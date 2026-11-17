/*
 * Copyright (c) 2003 Fabrice Bellard
 *
 * This file is part of FFmpeg.
 *
 * FFmpeg is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * FFmpeg is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with FFmpeg; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
 */

/*
 * ffplay-custom: this is a modified version of fftools/ffplay.c from FFmpeg 6.1.1.
 * Modified by Cine, first changed in 2026 (the dates of later changes are in the git history of the
 * ffplay-custom repository, and the list of changes is in its CHANGELOG.md).
 * It is still licensed under the GNU Lesser General Public License, version 2.1 or later, like the original.
 */

/**
 * @file
 * simple media player based on the FFmpeg libraries
 */

#include "config.h"
#include "config_components.h"
#include <inttypes.h>
#include <math.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>

#include "libavutil/avstring.h"
#include "libavutil/channel_layout.h"
#include "libavutil/eval.h"
#include "libavutil/mathematics.h"
#include "libavutil/pixdesc.h"
#include "libavutil/imgutils.h"
#include "libavutil/dict.h"
#include "libavutil/fifo.h"
#include "libavutil/parseutils.h"
#include "libavutil/samplefmt.h"
#include "libavutil/time.h"
#include "libavutil/bprint.h"
#include "libavformat/avformat.h"
#include "libavdevice/avdevice.h"
#include "libswscale/swscale.h"
#include "libavutil/opt.h"
#include "libavutil/tx.h"
#include "libswresample/swresample.h"

#include "libavfilter/avfilter.h"
#include "libavfilter/buffersink.h"
#include "libavfilter/buffersrc.h"

#include <SDL.h>
#include <SDL_thread.h>

#include "cmdutils.h"
#include "opt_common.h"

const char program_name[] = "ffplay";
const int program_birth_year = 2003;

#define MAX_QUEUE_SIZE (64 * 1024 * 1024)       /* big: audio keeps flowing while the picture is late */
#define MIN_FRAMES 25
#define EXTERNAL_CLOCK_MIN_FRAMES 2
#define EXTERNAL_CLOCK_MAX_FRAMES 10

/* Minimum SDL audio buffer size, in samples. */
#define SDL_AUDIO_MIN_BUFFER_SIZE 512
/* Calculate actual buffer size keeping in mind not cause too frequent audio callbacks */
#define SDL_AUDIO_MAX_CALLBACKS_PER_SEC 30

/* Step size for volume control in dB */
#define SDL_VOLUME_STEP (0.75)

/* no AV sync correction is done if below the minimum AV sync threshold */
#define AV_SYNC_THRESHOLD_MIN 0.04
/* AV sync correction is done if above the maximum AV sync threshold */
#define AV_SYNC_THRESHOLD_MAX 0.1
/* If a frame duration is longer than this, it will not be duplicated to compensate AV sync */
#define AV_SYNC_FRAMEDUP_THRESHOLD 0.1
/* no AV correction is done if too big error */
#define AV_NOSYNC_THRESHOLD 10.0

/* maximum audio speed change to get correct sync */
#define SAMPLE_CORRECTION_PERCENT_MAX 10

/* external clock speed adjustment constants for realtime sources based on buffer fullness */
#define EXTERNAL_CLOCK_SPEED_MIN  0.900
#define EXTERNAL_CLOCK_SPEED_MAX  1.010
#define EXTERNAL_CLOCK_SPEED_STEP 0.001

/* we use about AUDIO_DIFF_AVG_NB A-V differences to make the average */
#define AUDIO_DIFF_AVG_NB   20

/* polls for possible required screen refresh at least this often, should be less than 1/fps */
#define REFRESH_RATE 0.01

/* NOTE: the size must be big enough to compensate the hardware audio buffersize size */
/* TODO: We assume that a decoded and resampled frame fits into this buffer */
#define SAMPLE_ARRAY_SIZE (8 * 65536)

#define CURSOR_HIDE_DELAY cfg_hide_delay

#define USE_ONEPASS_SUBTITLE_RENDER 1

typedef struct MyAVPacketList {
    AVPacket *pkt;
    int serial;
} MyAVPacketList;

typedef struct PacketQueue {
    AVFifo *pkt_list;
    int nb_packets;
    int size;
    int64_t duration;
    int abort_request;
    int serial;
    SDL_mutex *mutex;
    SDL_cond *cond;
} PacketQueue;

#define VIDEO_PICTURE_QUEUE_SIZE 3
#define SUBPICTURE_QUEUE_SIZE 16
#define SAMPLE_QUEUE_SIZE 9
#define FRAME_QUEUE_SIZE FFMAX(SAMPLE_QUEUE_SIZE, FFMAX(VIDEO_PICTURE_QUEUE_SIZE, SUBPICTURE_QUEUE_SIZE))

typedef struct AudioParams {
    int freq;
    AVChannelLayout ch_layout;
    enum AVSampleFormat fmt;
    int frame_size;
    int bytes_per_sec;
} AudioParams;

typedef struct Clock {
    double pts;           /* clock base */
    double pts_drift;     /* clock base minus time at which we updated the clock */
    double last_updated;
    double speed;
    int serial;           /* clock is based on a packet with this serial */
    int paused;
    int *queue_serial;    /* pointer to the current packet queue serial, used for obsolete clock detection */
} Clock;

typedef struct FrameData {
    int64_t pkt_pos;
} FrameData;

/* Common struct for handling all types of decoded data and allocated render buffers. */
typedef struct Frame {
    AVFrame *frame;
    AVSubtitle sub;
    int serial;
    double pts;           /* presentation timestamp for the frame */
    double duration;      /* estimated duration of the frame */
    int64_t pos;          /* byte position of the frame in the input file */
    int width;
    int height;
    int format;
    AVRational sar;
    int uploaded;
    int flip_v;
} Frame;

typedef struct FrameQueue {
    Frame queue[FRAME_QUEUE_SIZE];
    int rindex;
    int windex;
    int size;
    int max_size;
    int keep_last;
    int rindex_shown;
    SDL_mutex *mutex;
    SDL_cond *cond;
    PacketQueue *pktq;
} FrameQueue;

enum {
    AV_SYNC_AUDIO_MASTER, /* default choice */
    AV_SYNC_VIDEO_MASTER,
    AV_SYNC_EXTERNAL_CLOCK, /* synchronize to an external clock */
};

typedef struct Decoder {
    AVPacket *pkt;
    PacketQueue *queue;
    AVCodecContext *avctx;
    int pkt_serial;
    int finished;
    int packet_pending;
    SDL_cond *empty_queue_cond;
    int64_t start_pts;
    AVRational start_pts_tb;
    int64_t next_pts;
    AVRational next_pts_tb;
    SDL_Thread *decoder_tid;
} Decoder;

typedef struct VideoState {
    SDL_Thread *read_tid;
    const AVInputFormat *iformat;
    int abort_request;
    int force_refresh;
    int paused;
    int last_paused;
    int queue_attachments_req;
    int seek_req;
    int seek_flags;
    int64_t seek_pos;
    int64_t seek_rel;
    int read_pause_return;
    AVFormatContext *ic;
    int realtime;

    Clock audclk;
    Clock vidclk;
    Clock extclk;

    FrameQueue pictq;
    FrameQueue subpq;
    FrameQueue sampq;

    Decoder auddec;
    Decoder viddec;
    Decoder subdec;

    int audio_stream;

    int av_sync_type;

    double audio_clock;
    int audio_clock_serial;
    double audio_diff_cum; /* used for AV difference average computation */
    double audio_diff_avg_coef;
    double audio_diff_threshold;
    int audio_diff_avg_count;
    AVStream *audio_st;
    PacketQueue audioq;
    int audio_hw_buf_size;
    uint8_t *audio_buf;
    uint8_t *audio_buf1;
    unsigned int audio_buf_size; /* in bytes */
    unsigned int audio_buf1_size;
    int audio_buf_index; /* in bytes */
    int audio_write_buf_size;
    int audio_volume;
    float xf_gain;              /* 0 to 1: how loud this stream is during a crossfade */
    SDL_AudioDeviceID audio_dev_id;  /* this stream's own audio device (two streams play during a crossfade) */
    float level;                /* how loud the sound going out is (0 to 1), for the cover art backdrop */
    unsigned stream_id;         /* a number that is different for every stream that is opened */
    int muted;
    struct AudioParams audio_src;
    struct AudioParams audio_filter_src;
    struct AudioParams audio_tgt;
    struct SwrContext *swr_ctx;
    int frame_drops_early;
    int frame_drops_late;

    enum ShowMode {
        SHOW_MODE_NONE = -1, SHOW_MODE_VIDEO = 0, SHOW_MODE_WAVES, SHOW_MODE_RDFT, SHOW_MODE_NB
    } show_mode;
    int16_t sample_array[SAMPLE_ARRAY_SIZE];
    int sample_array_index;
    int last_i_start;
    AVTXContext *rdft;
    av_tx_fn rdft_fn;
    int rdft_bits;
    float *real_data;
    AVComplexFloat *rdft_data;
    int xpos;
    double last_vis_time;
    SDL_Texture *vis_texture;
    SDL_Texture *sub_texture;
    SDL_Texture *vid_texture;

    int subtitle_stream;
    AVStream *subtitle_st;
    PacketQueue subtitleq;

    double frame_timer;
    double frame_last_returned_time;
    double frame_last_filter_delay;
    int video_stream;
    AVStream *video_st;
    PacketQueue videoq;
    double max_frame_duration;      // maximum duration of a frame - above this, we consider the jump a timestamp discontinuity
    struct SwsContext *sub_convert_ctx;
    int eof;
    int seek_precise;           /* the seek in progress must land exactly on its time */
    int prec_v, prec_a;         /* 1 = pictures / sound before prec_target are still being skipped */
    int prec_ser_v, prec_ser_a; /* the queue serial those frames belong to */
    double prec_target;         /* seconds */
    volatile int ui_hold;       /* the reader saw the end of the last video: pause on its last picture */
    int ui_held;                /* 0 = not held, 1 = paused on the last picture, 2 = restarting */
    int ui_thumb_id;            /* the seek previews of this stream: 0 = not started, -1 = none, else their number */

    char *filename;
    int width, height, xleft, ytop;
    int step;

    int vfilter_idx;
    AVFilterContext *in_video_filter;   // the first filter in the video chain
    AVFilterContext *out_video_filter;  // the last filter in the video chain
    AVFilterContext *in_audio_filter;   // the first filter in the audio chain
    AVFilterContext *out_audio_filter;  // the last filter in the audio chain
    AVFilterGraph *agraph;              // audio filter graph

    int last_video_stream, last_audio_stream, last_subtitle_stream;

    SDL_cond *continue_read_thread;
} VideoState;

/* options specified by the user */
static const AVInputFormat *file_iformat;
static const char *input_filename;
static const char *window_title;
static int default_width  = 640;
static int default_height = 480;
static int screen_width  = 0;
static int screen_height = 0;
static int screen_left = SDL_WINDOWPOS_CENTERED;
static int screen_top = SDL_WINDOWPOS_CENTERED;
static int audio_disable;
static int video_disable;
static int subtitle_disable;
static const char* wanted_stream_spec[AVMEDIA_TYPE_NB] = {0};
static int seek_by_bytes = -1;
static float seek_interval = 10;
static int display_disable;
static int borderless = 1;
static int alwaysontop;
static int startup_volume = 100;
static int show_status = -1;
static int av_sync_type = AV_SYNC_AUDIO_MASTER;
static int64_t start_time = AV_NOPTS_VALUE;
static int64_t duration = AV_NOPTS_VALUE;
static int fast = 0;
static int genpts = 0;
static int lowres = 0;
static int decoder_reorder_pts = -1;
static int autoexit = 1;
static int exit_on_keydown;
static int exit_on_mousedown;
static int loop = 1;
static int framedrop = -1;
static int infinite_buffer = -1;
static enum ShowMode show_mode = SHOW_MODE_NONE;
static const char *audio_codec_name;
static const char *subtitle_codec_name;
static const char *video_codec_name;
double rdftspeed = 0.02;
static int64_t cursor_last_shown;
static int cursor_hidden = 0;
static const char **vfilters_list = NULL;
static int nb_vfilters = 0;
static char *afilters = NULL;
static int autorotate = 1;
static int find_stream_info = 1;
static int filter_nbthreads = 0;

/* current context */
static int is_full_screen = 1;
static int64_t audio_callback_time;

#define FF_QUIT_EVENT    (SDL_USEREVENT + 2)

static SDL_Window *window;
static SDL_Renderer *renderer;
static SDL_RendererInfo renderer_info = {0};
static SDL_AudioDeviceID audio_dev;

static const struct TextureFormatEntry {
    enum AVPixelFormat format;
    int texture_fmt;
} sdl_texture_format_map[] = {
    { AV_PIX_FMT_RGB8,           SDL_PIXELFORMAT_RGB332 },
    { AV_PIX_FMT_RGB444,         SDL_PIXELFORMAT_RGB444 },
    { AV_PIX_FMT_RGB555,         SDL_PIXELFORMAT_RGB555 },
    { AV_PIX_FMT_BGR555,         SDL_PIXELFORMAT_BGR555 },
    { AV_PIX_FMT_RGB565,         SDL_PIXELFORMAT_RGB565 },
    { AV_PIX_FMT_BGR565,         SDL_PIXELFORMAT_BGR565 },
    { AV_PIX_FMT_RGB24,          SDL_PIXELFORMAT_RGB24 },
    { AV_PIX_FMT_BGR24,          SDL_PIXELFORMAT_BGR24 },
    { AV_PIX_FMT_0RGB32,         SDL_PIXELFORMAT_RGB888 },
    { AV_PIX_FMT_0BGR32,         SDL_PIXELFORMAT_BGR888 },
    { AV_PIX_FMT_NE(RGB0, 0BGR), SDL_PIXELFORMAT_RGBX8888 },
    { AV_PIX_FMT_NE(BGR0, 0RGB), SDL_PIXELFORMAT_BGRX8888 },
    { AV_PIX_FMT_RGB32,          SDL_PIXELFORMAT_ARGB8888 },
    { AV_PIX_FMT_RGB32_1,        SDL_PIXELFORMAT_RGBA8888 },
    { AV_PIX_FMT_BGR32,          SDL_PIXELFORMAT_ABGR8888 },
    { AV_PIX_FMT_BGR32_1,        SDL_PIXELFORMAT_BGRA8888 },
    { AV_PIX_FMT_YUV420P,        SDL_PIXELFORMAT_IYUV },
    { AV_PIX_FMT_YUYV422,        SDL_PIXELFORMAT_YUY2 },
    { AV_PIX_FMT_UYVY422,        SDL_PIXELFORMAT_UYVY },
    { AV_PIX_FMT_NONE,           SDL_PIXELFORMAT_UNKNOWN },
};

static int opt_add_vfilter(void *optctx, const char *opt, const char *arg)
{
    int ret = GROW_ARRAY(vfilters_list, nb_vfilters);
    if (ret < 0)
        return ret;

    vfilters_list[nb_vfilters - 1] = arg;
    return 0;
}

static inline
int cmp_audio_fmts(enum AVSampleFormat fmt1, int64_t channel_count1,
                   enum AVSampleFormat fmt2, int64_t channel_count2)
{
    /* If channel count == 1, planar and non-planar formats are the same */
    if (channel_count1 == 1 && channel_count2 == 1)
        return av_get_packed_sample_fmt(fmt1) != av_get_packed_sample_fmt(fmt2);
    else
        return channel_count1 != channel_count2 || fmt1 != fmt2;
}

static int packet_queue_put_private(PacketQueue *q, AVPacket *pkt)
{
    MyAVPacketList pkt1;
    int ret;

    if (q->abort_request)
       return -1;


    pkt1.pkt = pkt;
    pkt1.serial = q->serial;

    ret = av_fifo_write(q->pkt_list, &pkt1, 1);
    if (ret < 0)
        return ret;
    q->nb_packets++;
    q->size += pkt1.pkt->size + sizeof(pkt1);
    q->duration += pkt1.pkt->duration;
    /* XXX: should duplicate packet data in DV case */
    SDL_CondSignal(q->cond);
    return 0;
}

static int packet_queue_put(PacketQueue *q, AVPacket *pkt)
{
    AVPacket *pkt1;
    int ret;

    pkt1 = av_packet_alloc();
    if (!pkt1) {
        av_packet_unref(pkt);
        return -1;
    }
    av_packet_move_ref(pkt1, pkt);

    SDL_LockMutex(q->mutex);
    ret = packet_queue_put_private(q, pkt1);
    SDL_UnlockMutex(q->mutex);

    if (ret < 0)
        av_packet_free(&pkt1);

    return ret;
}

static int packet_queue_put_nullpacket(PacketQueue *q, AVPacket *pkt, int stream_index)
{
    pkt->stream_index = stream_index;
    return packet_queue_put(q, pkt);
}

/* packet queue handling */
static int packet_queue_init(PacketQueue *q)
{
    memset(q, 0, sizeof(PacketQueue));
    q->pkt_list = av_fifo_alloc2(1, sizeof(MyAVPacketList), AV_FIFO_FLAG_AUTO_GROW);
    if (!q->pkt_list)
        return AVERROR(ENOMEM);
    q->mutex = SDL_CreateMutex();
    if (!q->mutex) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateMutex(): %s\n", SDL_GetError());
        return AVERROR(ENOMEM);
    }
    q->cond = SDL_CreateCond();
    if (!q->cond) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateCond(): %s\n", SDL_GetError());
        return AVERROR(ENOMEM);
    }
    q->abort_request = 1;
    return 0;
}

static void packet_queue_flush(PacketQueue *q)
{
    MyAVPacketList pkt1;

    SDL_LockMutex(q->mutex);
    while (av_fifo_read(q->pkt_list, &pkt1, 1) >= 0)
        av_packet_free(&pkt1.pkt);
    q->nb_packets = 0;
    q->size = 0;
    q->duration = 0;
    q->serial++;
    SDL_UnlockMutex(q->mutex);
}

static void packet_queue_destroy(PacketQueue *q)
{
    packet_queue_flush(q);
    av_fifo_freep2(&q->pkt_list);
    SDL_DestroyMutex(q->mutex);
    SDL_DestroyCond(q->cond);
}

static void packet_queue_abort(PacketQueue *q)
{
    SDL_LockMutex(q->mutex);

    q->abort_request = 1;

    SDL_CondSignal(q->cond);

    SDL_UnlockMutex(q->mutex);
}

static void packet_queue_start(PacketQueue *q)
{
    SDL_LockMutex(q->mutex);
    q->abort_request = 0;
    q->serial++;
    SDL_UnlockMutex(q->mutex);
}

/* return < 0 if aborted, 0 if no packet and > 0 if packet.  */
static int packet_queue_get(PacketQueue *q, AVPacket *pkt, int block, int *serial)
{
    MyAVPacketList pkt1;
    int ret;

    SDL_LockMutex(q->mutex);

    for (;;) {
        if (q->abort_request) {
            ret = -1;
            break;
        }

        if (av_fifo_read(q->pkt_list, &pkt1, 1) >= 0) {
            q->nb_packets--;
            q->size -= pkt1.pkt->size + sizeof(pkt1);
            q->duration -= pkt1.pkt->duration;
            av_packet_move_ref(pkt, pkt1.pkt);
            if (serial)
                *serial = pkt1.serial;
            av_packet_free(&pkt1.pkt);
            ret = 1;
            break;
        } else if (!block) {
            ret = 0;
            break;
        } else {
            SDL_CondWait(q->cond, q->mutex);
        }
    }
    SDL_UnlockMutex(q->mutex);
    return ret;
}

static int decoder_init(Decoder *d, AVCodecContext *avctx, PacketQueue *queue, SDL_cond *empty_queue_cond) {
    memset(d, 0, sizeof(Decoder));
    d->pkt = av_packet_alloc();
    if (!d->pkt)
        return AVERROR(ENOMEM);
    d->avctx = avctx;
    d->queue = queue;
    d->empty_queue_cond = empty_queue_cond;
    d->start_pts = AV_NOPTS_VALUE;
    d->pkt_serial = -1;
    return 0;
}

static int decoder_decode_frame(Decoder *d, AVFrame *frame, AVSubtitle *sub) {
    int ret = AVERROR(EAGAIN);

    for (;;) {
        if (d->queue->serial == d->pkt_serial) {
            do {
                if (d->queue->abort_request)
                    return -1;

                switch (d->avctx->codec_type) {
                    case AVMEDIA_TYPE_VIDEO:
                        ret = avcodec_receive_frame(d->avctx, frame);
                        if (ret >= 0) {
                            if (decoder_reorder_pts == -1) {
                                frame->pts = frame->best_effort_timestamp;
                            } else if (!decoder_reorder_pts) {
                                frame->pts = frame->pkt_dts;
                            }
                        }
                        break;
                    case AVMEDIA_TYPE_AUDIO:
                        ret = avcodec_receive_frame(d->avctx, frame);
                        if (ret >= 0) {
                            AVRational tb = (AVRational){1, frame->sample_rate};
                            if (frame->pts != AV_NOPTS_VALUE)
                                frame->pts = av_rescale_q(frame->pts, d->avctx->pkt_timebase, tb);
                            else if (d->next_pts != AV_NOPTS_VALUE)
                                frame->pts = av_rescale_q(d->next_pts, d->next_pts_tb, tb);
                            if (frame->pts != AV_NOPTS_VALUE) {
                                d->next_pts = frame->pts + frame->nb_samples;
                                d->next_pts_tb = tb;
                            }
                        }
                        break;
                }
                if (ret == AVERROR_EOF) {
                    d->finished = d->pkt_serial;
                    avcodec_flush_buffers(d->avctx);
                    return 0;
                }
                if (ret >= 0)
                    return 1;
            } while (ret != AVERROR(EAGAIN));
        }

        do {
            if (d->queue->nb_packets == 0)
                SDL_CondSignal(d->empty_queue_cond);
            if (d->packet_pending) {
                d->packet_pending = 0;
            } else {
                int old_serial = d->pkt_serial;
                if (packet_queue_get(d->queue, d->pkt, 1, &d->pkt_serial) < 0)
                    return -1;
                if (old_serial != d->pkt_serial) {
                    avcodec_flush_buffers(d->avctx);
                    d->finished = 0;
                    d->next_pts = d->start_pts;
                    d->next_pts_tb = d->start_pts_tb;
                }
            }
            if (d->queue->serial == d->pkt_serial)
                break;
            av_packet_unref(d->pkt);
        } while (1);

        if (d->avctx->codec_type == AVMEDIA_TYPE_SUBTITLE) {
            int got_frame = 0;
            ret = avcodec_decode_subtitle2(d->avctx, sub, &got_frame, d->pkt);
            if (ret < 0) {
                ret = AVERROR(EAGAIN);
            } else {
                if (got_frame && !d->pkt->data) {
                    d->packet_pending = 1;
                }
                ret = got_frame ? 0 : (d->pkt->data ? AVERROR(EAGAIN) : AVERROR_EOF);
            }
            av_packet_unref(d->pkt);
        } else {
            if (d->pkt->buf && !d->pkt->opaque_ref) {
                FrameData *fd;

                d->pkt->opaque_ref = av_buffer_allocz(sizeof(*fd));
                if (!d->pkt->opaque_ref)
                    return AVERROR(ENOMEM);
                fd = (FrameData*)d->pkt->opaque_ref->data;
                fd->pkt_pos = d->pkt->pos;
            }

            if (avcodec_send_packet(d->avctx, d->pkt) == AVERROR(EAGAIN)) {
                av_log(d->avctx, AV_LOG_ERROR, "Receive_frame and send_packet both returned EAGAIN, which is an API violation.\n");
                d->packet_pending = 1;
            } else {
                av_packet_unref(d->pkt);
            }
        }
    }
}

static void decoder_destroy(Decoder *d) {
    av_packet_free(&d->pkt);
    avcodec_free_context(&d->avctx);
}

static void frame_queue_unref_item(Frame *vp)
{
    av_frame_unref(vp->frame);
    avsubtitle_free(&vp->sub);
}

static int frame_queue_init(FrameQueue *f, PacketQueue *pktq, int max_size, int keep_last)
{
    int i;
    memset(f, 0, sizeof(FrameQueue));
    if (!(f->mutex = SDL_CreateMutex())) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateMutex(): %s\n", SDL_GetError());
        return AVERROR(ENOMEM);
    }
    if (!(f->cond = SDL_CreateCond())) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateCond(): %s\n", SDL_GetError());
        return AVERROR(ENOMEM);
    }
    f->pktq = pktq;
    f->max_size = FFMIN(max_size, FRAME_QUEUE_SIZE);
    f->keep_last = !!keep_last;
    for (i = 0; i < f->max_size; i++)
        if (!(f->queue[i].frame = av_frame_alloc()))
            return AVERROR(ENOMEM);
    return 0;
}

static void frame_queue_destroy(FrameQueue *f)
{
    int i;
    for (i = 0; i < f->max_size; i++) {
        Frame *vp = &f->queue[i];
        frame_queue_unref_item(vp);
        av_frame_free(&vp->frame);
    }
    SDL_DestroyMutex(f->mutex);
    SDL_DestroyCond(f->cond);
}

static void frame_queue_signal(FrameQueue *f)
{
    SDL_LockMutex(f->mutex);
    SDL_CondSignal(f->cond);
    SDL_UnlockMutex(f->mutex);
}

static Frame *frame_queue_peek(FrameQueue *f)
{
    return &f->queue[(f->rindex + f->rindex_shown) % f->max_size];
}

static Frame *frame_queue_peek_next(FrameQueue *f)
{
    return &f->queue[(f->rindex + f->rindex_shown + 1) % f->max_size];
}

static Frame *frame_queue_peek_last(FrameQueue *f)
{
    return &f->queue[f->rindex];
}

static Frame *frame_queue_peek_writable(FrameQueue *f)
{
    /* wait until we have space to put a new frame */
    SDL_LockMutex(f->mutex);
    while (f->size >= f->max_size &&
           !f->pktq->abort_request) {
        SDL_CondWait(f->cond, f->mutex);
    }
    SDL_UnlockMutex(f->mutex);

    if (f->pktq->abort_request)
        return NULL;

    return &f->queue[f->windex];
}

static Frame *frame_queue_peek_readable(FrameQueue *f)
{
    /* wait until we have a readable a new frame */
    SDL_LockMutex(f->mutex);
    while (f->size - f->rindex_shown <= 0 &&
           !f->pktq->abort_request) {
        SDL_CondWait(f->cond, f->mutex);
    }
    SDL_UnlockMutex(f->mutex);

    if (f->pktq->abort_request)
        return NULL;

    return &f->queue[(f->rindex + f->rindex_shown) % f->max_size];
}

static void frame_queue_push(FrameQueue *f)
{
    if (++f->windex == f->max_size)
        f->windex = 0;
    SDL_LockMutex(f->mutex);
    f->size++;
    SDL_CondSignal(f->cond);
    SDL_UnlockMutex(f->mutex);
}

static void frame_queue_next(FrameQueue *f)
{
    if (f->keep_last && !f->rindex_shown) {
        f->rindex_shown = 1;
        return;
    }
    frame_queue_unref_item(&f->queue[f->rindex]);
    if (++f->rindex == f->max_size)
        f->rindex = 0;
    SDL_LockMutex(f->mutex);
    f->size--;
    SDL_CondSignal(f->cond);
    SDL_UnlockMutex(f->mutex);
}

/* return the number of undisplayed frames in the queue */
static int frame_queue_nb_remaining(FrameQueue *f)
{
    return f->size - f->rindex_shown;
}

/* return last shown position */
static int64_t frame_queue_last_pos(FrameQueue *f)
{
    Frame *fp = &f->queue[f->rindex];
    if (f->rindex_shown && fp->serial == f->pktq->serial)
        return fp->pos;
    else
        return -1;
}

static void decoder_abort(Decoder *d, FrameQueue *fq)
{
    packet_queue_abort(d->queue);
    frame_queue_signal(fq);
    SDL_WaitThread(d->decoder_tid, NULL);
    d->decoder_tid = NULL;
    packet_queue_flush(d->queue);
}

static inline void fill_rectangle(int x, int y, int w, int h)
{
    SDL_Rect rect;
    rect.x = x;
    rect.y = y;
    rect.w = w;
    rect.h = h;
    if (w && h)
        SDL_RenderFillRect(renderer, &rect);
}

static int realloc_texture(SDL_Texture **texture, Uint32 new_format, int new_width, int new_height, SDL_BlendMode blendmode, int init_texture)
{
    Uint32 format;
    int access, w, h;
    if (!*texture || SDL_QueryTexture(*texture, &format, &access, &w, &h) < 0 || new_width != w || new_height != h || new_format != format) {
        void *pixels;
        int pitch;
        if (*texture)
            SDL_DestroyTexture(*texture);
        if (!(*texture = SDL_CreateTexture(renderer, new_format, SDL_TEXTUREACCESS_STREAMING, new_width, new_height)))
            return -1;
        if (SDL_SetTextureBlendMode(*texture, blendmode) < 0)
            return -1;
        if (init_texture) {
            if (SDL_LockTexture(*texture, NULL, &pixels, &pitch) < 0)
                return -1;
            memset(pixels, 0, pitch * new_height);
            SDL_UnlockTexture(*texture);
        }
        av_log(NULL, AV_LOG_VERBOSE, "Created %dx%d texture with %s.\n", new_width, new_height, SDL_GetPixelFormatName(new_format));
    }
    return 0;
}

static void calculate_display_rect(SDL_Rect *rect,
                                   int scr_xleft, int scr_ytop, int scr_width, int scr_height,
                                   int pic_width, int pic_height, AVRational pic_sar)
{
    AVRational aspect_ratio = pic_sar;
    int64_t width, height, x, y;

    if (av_cmp_q(aspect_ratio, av_make_q(0, 1)) <= 0)
        aspect_ratio = av_make_q(1, 1);

    aspect_ratio = av_mul_q(aspect_ratio, av_make_q(pic_width, pic_height));

    /* XXX: we suppose the screen has a 1.0 pixel ratio */
    height = scr_height;
    width = av_rescale(height, aspect_ratio.num, aspect_ratio.den) & ~1;
    if (width > scr_width) {
        width = scr_width;
        height = av_rescale(width, aspect_ratio.den, aspect_ratio.num) & ~1;
    }
    x = (scr_width - width) / 2;
    y = (scr_height - height) / 2;
    rect->x = scr_xleft + x;
    rect->y = scr_ytop  + y;
    rect->w = FFMAX((int)width,  1);
    rect->h = FFMAX((int)height, 1);
}

static void get_sdl_pix_fmt_and_blendmode(int format, Uint32 *sdl_pix_fmt, SDL_BlendMode *sdl_blendmode)
{
    int i;
    *sdl_blendmode = SDL_BLENDMODE_NONE;
    *sdl_pix_fmt = SDL_PIXELFORMAT_UNKNOWN;
    if (format == AV_PIX_FMT_RGB32   ||
        format == AV_PIX_FMT_RGB32_1 ||
        format == AV_PIX_FMT_BGR32   ||
        format == AV_PIX_FMT_BGR32_1)
        *sdl_blendmode = SDL_BLENDMODE_BLEND;
    for (i = 0; i < FF_ARRAY_ELEMS(sdl_texture_format_map) - 1; i++) {
        if (format == sdl_texture_format_map[i].format) {
            *sdl_pix_fmt = sdl_texture_format_map[i].texture_fmt;
            return;
        }
    }
}

static int upload_texture(SDL_Texture **tex, AVFrame *frame)
{
    int ret = 0;
    Uint32 sdl_pix_fmt;
    SDL_BlendMode sdl_blendmode;
    get_sdl_pix_fmt_and_blendmode(frame->format, &sdl_pix_fmt, &sdl_blendmode);
    if (realloc_texture(tex, sdl_pix_fmt == SDL_PIXELFORMAT_UNKNOWN ? SDL_PIXELFORMAT_ARGB8888 : sdl_pix_fmt, frame->width, frame->height, sdl_blendmode, 0) < 0)
        return -1;
    switch (sdl_pix_fmt) {
        case SDL_PIXELFORMAT_IYUV:
            if (frame->linesize[0] > 0 && frame->linesize[1] > 0 && frame->linesize[2] > 0) {
                ret = SDL_UpdateYUVTexture(*tex, NULL, frame->data[0], frame->linesize[0],
                                                       frame->data[1], frame->linesize[1],
                                                       frame->data[2], frame->linesize[2]);
            } else if (frame->linesize[0] < 0 && frame->linesize[1] < 0 && frame->linesize[2] < 0) {
                ret = SDL_UpdateYUVTexture(*tex, NULL, frame->data[0] + frame->linesize[0] * (frame->height                    - 1), -frame->linesize[0],
                                                       frame->data[1] + frame->linesize[1] * (AV_CEIL_RSHIFT(frame->height, 1) - 1), -frame->linesize[1],
                                                       frame->data[2] + frame->linesize[2] * (AV_CEIL_RSHIFT(frame->height, 1) - 1), -frame->linesize[2]);
            } else {
                av_log(NULL, AV_LOG_ERROR, "Mixed negative and positive linesizes are not supported.\n");
                return -1;
            }
            break;
        default:
            if (frame->linesize[0] < 0) {
                ret = SDL_UpdateTexture(*tex, NULL, frame->data[0] + frame->linesize[0] * (frame->height - 1), -frame->linesize[0]);
            } else {
                ret = SDL_UpdateTexture(*tex, NULL, frame->data[0], frame->linesize[0]);
            }
            break;
    }
    return ret;
}

static void set_sdl_yuv_conversion_mode(AVFrame *frame)
{
#if SDL_VERSION_ATLEAST(2,0,8)
    SDL_YUV_CONVERSION_MODE mode = SDL_YUV_CONVERSION_AUTOMATIC;
    if (frame && (frame->format == AV_PIX_FMT_YUV420P || frame->format == AV_PIX_FMT_YUYV422 || frame->format == AV_PIX_FMT_UYVY422)) {
        if (frame->color_range == AVCOL_RANGE_JPEG)
            mode = SDL_YUV_CONVERSION_JPEG;
        else if (frame->colorspace == AVCOL_SPC_BT709)
            mode = SDL_YUV_CONVERSION_BT709;
        else if (frame->colorspace == AVCOL_SPC_BT470BG || frame->colorspace == AVCOL_SPC_SMPTE170M)
            mode = SDL_YUV_CONVERSION_BT601;
    }
    SDL_SetYUVConversionMode(mode); /* FIXME: no support for linear transfer */
#endif
}

static void ui_cover_backdrop(VideoState *is, int flip);
static int ui_has_cover(VideoState *is);
static void ui_flow_draw(VideoState *is);
static int ui_flow_wants_redraw(VideoState *is);
static int ui_flow_video(VideoState *is);
static void ui_live_grab(VideoState *is, const SDL_Rect *rect, int flip);
static void ui_xf_video_draw(VideoState *is, int to_tile);
static double ui_vflow_p = 0.0;         /* 0 to 1: how far the playing video has shrunk into its tile (it animates when L is pressed) */
static double ui_vflow_ep = 0.0;        /* the same, eased: slow, quick, slow */
static int64_t ui_vflow_t = 0;          /* when the animation was last stepped */
static SDL_Rect ui_live_rect;           /* where the video is drawn full screen (set in video_image_display) */
static int ui_live_ok = 0;              /* 1 = the frame on screen was copied into ui_live_tex in this drawing */
static SDL_Texture *ui_live_tex = NULL; /* the frame on screen, as a picture of its own for the tile */
static int ui_live_w = 0, ui_live_h = 0;
static void ui_flow_swipe(VideoState *is, SDL_Event *ev);

static void video_image_display(VideoState *is)
{
    Frame *vp;
    Frame *sp = NULL;
    SDL_Rect rect;

    vp = frame_queue_peek_last(&is->pictq);
    if (is->subtitle_st) {
        if (frame_queue_nb_remaining(&is->subpq) > 0) {
            sp = frame_queue_peek(&is->subpq);

            if (vp->pts >= sp->pts + ((float) sp->sub.start_display_time / 1000)) {
                if (!sp->uploaded) {
                    uint8_t* pixels[4];
                    int pitch[4];
                    int i;
                    if (!sp->width || !sp->height) {
                        sp->width = vp->width;
                        sp->height = vp->height;
                    }
                    if (realloc_texture(&is->sub_texture, SDL_PIXELFORMAT_ARGB8888, sp->width, sp->height, SDL_BLENDMODE_BLEND, 1) < 0)
                        return;

                    for (i = 0; i < sp->sub.num_rects; i++) {
                        AVSubtitleRect *sub_rect = sp->sub.rects[i];

                        sub_rect->x = av_clip(sub_rect->x, 0, sp->width );
                        sub_rect->y = av_clip(sub_rect->y, 0, sp->height);
                        sub_rect->w = av_clip(sub_rect->w, 0, sp->width  - sub_rect->x);
                        sub_rect->h = av_clip(sub_rect->h, 0, sp->height - sub_rect->y);

                        is->sub_convert_ctx = sws_getCachedContext(is->sub_convert_ctx,
                            sub_rect->w, sub_rect->h, AV_PIX_FMT_PAL8,
                            sub_rect->w, sub_rect->h, AV_PIX_FMT_BGRA,
                            0, NULL, NULL, NULL);
                        if (!is->sub_convert_ctx) {
                            av_log(NULL, AV_LOG_FATAL, "Cannot initialize the conversion context\n");
                            return;
                        }
                        if (!SDL_LockTexture(is->sub_texture, (SDL_Rect *)sub_rect, (void **)pixels, pitch)) {
                            sws_scale(is->sub_convert_ctx, (const uint8_t * const *)sub_rect->data, sub_rect->linesize,
                                      0, sub_rect->h, pixels, pitch);
                            SDL_UnlockTexture(is->sub_texture);
                        }
                    }
                    sp->uploaded = 1;
                }
            } else
                sp = NULL;
        }
    }

    calculate_display_rect(&rect, is->xleft, is->ytop, is->width, is->height, vp->width, vp->height, vp->sar);
    set_sdl_yuv_conversion_mode(vp->frame);

    if (!vp->uploaded) {
        if (upload_texture(&is->vid_texture, vp->frame) < 0) {
            set_sdl_yuv_conversion_mode(NULL);
            return;
        }
        vp->uploaded = 1;
        vp->flip_v = vp->frame->linesize[0] < 0;
    }

    ui_cover_backdrop(is, vp->flip_v);      /* behind the cover art: its own colors, glowing */
    ui_live_grab(is, &rect, vp->flip_v);    /* over a video: copy the frame, the tile shows it */
    if (!ui_has_cover(is) && !ui_flow_video(is))    /* a cover is drawn by the queue view instead (ui_flow_draw) */
    {
        SDL_RenderCopyEx(renderer, is->vid_texture, NULL, &rect, 0, NULL, vp->flip_v ? SDL_FLIP_VERTICAL : 0);
        ui_xf_video_draw(is, 0);                /* the next video fades in over the end of this one */
    }
    set_sdl_yuv_conversion_mode(NULL);
    if (sp) {
#if USE_ONEPASS_SUBTITLE_RENDER
        SDL_RenderCopy(renderer, is->sub_texture, NULL, &rect);
#else
        int i;
        double xratio = (double)rect.w / (double)sp->width;
        double yratio = (double)rect.h / (double)sp->height;
        for (i = 0; i < sp->sub.num_rects; i++) {
            SDL_Rect *sub_rect = (SDL_Rect*)sp->sub.rects[i];
            SDL_Rect target = {.x = rect.x + sub_rect->x * xratio,
                               .y = rect.y + sub_rect->y * yratio,
                               .w = sub_rect->w * xratio,
                               .h = sub_rect->h * yratio};
            SDL_RenderCopy(renderer, is->sub_texture, sub_rect, &target);
        }
#endif
    }
}

static inline int compute_mod(int a, int b)
{
    return a < 0 ? a%b + b : a%b;
}

static int ui_aurora_backdrop(VideoState *is) av_unused;
static int ui_bubble_backdrop(VideoState *is);

static void video_audio_display(VideoState *s)
{
    int i, i_start, x, y1, y, ys, delay, n, nb_display_channels;
    int ch, channels, h, h2;
    int64_t time_diff;
    int rdft_bits, nb_freq;

    if (ui_bubble_backdrop(s) && s->show_mode == SHOW_MODE_RDFT)
        return;                         /* the aurora is the picture; waves are drawn over it below */

    for (rdft_bits = 1; (1 << rdft_bits) < 2 * s->height; rdft_bits++)
        ;
    nb_freq = 1 << (rdft_bits - 1);

    /* compute display index : center on currently output samples */
    channels = s->audio_tgt.ch_layout.nb_channels;
    nb_display_channels = channels;
    if (!s->paused) {
        int data_used= s->show_mode == SHOW_MODE_WAVES ? s->width : (2*nb_freq);
        n = 2 * channels;
        delay = s->audio_write_buf_size;
        delay /= n;

        /* to be more precise, we take into account the time spent since
           the last buffer computation */
        if (audio_callback_time) {
            time_diff = av_gettime_relative() - audio_callback_time;
            delay -= (time_diff * s->audio_tgt.freq) / 1000000;
        }

        delay += 2 * data_used;
        if (delay < data_used)
            delay = data_used;

        i_start= x = compute_mod(s->sample_array_index - delay * channels, SAMPLE_ARRAY_SIZE);
        if (s->show_mode == SHOW_MODE_WAVES) {
            h = INT_MIN;
            for (i = 0; i < 1000; i += channels) {
                int idx = (SAMPLE_ARRAY_SIZE + x - i) % SAMPLE_ARRAY_SIZE;
                int a = s->sample_array[idx];
                int b = s->sample_array[(idx + 4 * channels) % SAMPLE_ARRAY_SIZE];
                int c = s->sample_array[(idx + 5 * channels) % SAMPLE_ARRAY_SIZE];
                int d = s->sample_array[(idx + 9 * channels) % SAMPLE_ARRAY_SIZE];
                int score = a - d;
                if (h < score && (b ^ c) < 0) {
                    h = score;
                    i_start = idx;
                }
            }
        }

        s->last_i_start = i_start;
    } else {
        i_start = s->last_i_start;
    }

    if (s->show_mode == SHOW_MODE_WAVES) {
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);

        /* total height for one channel */
        h = s->height / nb_display_channels;
        /* graph height / 2 */
        h2 = (h * 9) / 20;
        for (ch = 0; ch < nb_display_channels; ch++) {
            i = i_start + ch;
            y1 = s->ytop + ch * h + (h / 2); /* position of center line */
            for (x = 0; x < s->width; x++) {
                y = (s->sample_array[i] * h2) >> 15;
                if (y < 0) {
                    y = -y;
                    ys = y1 - y;
                } else {
                    ys = y1;
                }
                fill_rectangle(s->xleft + x, ys, 1, y);
                i += channels;
                if (i >= SAMPLE_ARRAY_SIZE)
                    i -= SAMPLE_ARRAY_SIZE;
            }
        }

        SDL_SetRenderDrawColor(renderer, 0, 0, 255, 255);

        for (ch = 1; ch < nb_display_channels; ch++) {
            y = s->ytop + ch * h;
            fill_rectangle(s->xleft, y, s->width, 1);
        }
    } else {
        int err = 0;
        if (realloc_texture(&s->vis_texture, SDL_PIXELFORMAT_ARGB8888, s->width, s->height, SDL_BLENDMODE_NONE, 1) < 0)
            return;

        if (s->xpos >= s->width)
            s->xpos = 0;
        nb_display_channels= FFMIN(nb_display_channels, 2);
        if (rdft_bits != s->rdft_bits) {
            const float rdft_scale = 1.0;
            av_tx_uninit(&s->rdft);
            av_freep(&s->real_data);
            av_freep(&s->rdft_data);
            s->rdft_bits = rdft_bits;
            s->real_data = av_malloc_array(nb_freq, 4 *sizeof(*s->real_data));
            s->rdft_data = av_malloc_array(nb_freq + 1, 2 *sizeof(*s->rdft_data));
            err = av_tx_init(&s->rdft, &s->rdft_fn, AV_TX_FLOAT_RDFT,
                             0, 1 << rdft_bits, &rdft_scale, 0);
        }
        if (err < 0 || !s->rdft_data) {
            av_log(NULL, AV_LOG_ERROR, "Failed to allocate buffers for RDFT, switching to waves display\n");
            s->show_mode = SHOW_MODE_WAVES;
        } else {
            float *data_in[2];
            AVComplexFloat *data[2];
            SDL_Rect rect = {.x = s->xpos, .y = 0, .w = 1, .h = s->height};
            uint32_t *pixels;
            int pitch;
            for (ch = 0; ch < nb_display_channels; ch++) {
                data_in[ch] = s->real_data + 2 * nb_freq * ch;
                data[ch] = s->rdft_data + nb_freq * ch;
                i = i_start + ch;
                for (x = 0; x < 2 * nb_freq; x++) {
                    double w = (x-nb_freq) * (1.0 / nb_freq);
                    data_in[ch][x] = s->sample_array[i] * (1.0 - w * w);
                    i += channels;
                    if (i >= SAMPLE_ARRAY_SIZE)
                        i -= SAMPLE_ARRAY_SIZE;
                }
                s->rdft_fn(s->rdft, data[ch], data_in[ch], sizeof(float));
                data[ch][0].im = data[ch][nb_freq].re;
                data[ch][nb_freq].re = 0;
            }
            /* Least efficient way to do this, we should of course
             * directly access it but it is more than fast enough. */
            if (!SDL_LockTexture(s->vis_texture, &rect, (void **)&pixels, &pitch)) {
                pitch >>= 2;
                pixels += pitch * s->height;
                for (y = 0; y < s->height; y++) {
                    double w = 1 / sqrt(nb_freq);
                    int a = sqrt(w * sqrt(data[0][y].re * data[0][y].re + data[0][y].im * data[0][y].im));
                    int b = (nb_display_channels == 2 ) ? sqrt(w * hypot(data[1][y].re, data[1][y].im))
                                                        : a;
                    a = FFMIN(a, 255);
                    b = FFMIN(b, 255);
                    pixels -= pitch;
                    *pixels = (a << 16) + (b << 8) + ((a+b) >> 1);
                }
                SDL_UnlockTexture(s->vis_texture);
            }
            SDL_RenderCopy(renderer, s->vis_texture, NULL, NULL);
        }
        if (!s->paused)
            s->xpos++;
    }
}

static void stream_component_close(VideoState *is, int stream_index)
{
    AVFormatContext *ic = is->ic;
    AVCodecParameters *codecpar;

    if (stream_index < 0 || stream_index >= ic->nb_streams)
        return;
    codecpar = ic->streams[stream_index]->codecpar;

    switch (codecpar->codec_type) {
    case AVMEDIA_TYPE_AUDIO:
        decoder_abort(&is->auddec, &is->sampq);
        SDL_CloseAudioDevice(is->audio_dev_id);
        decoder_destroy(&is->auddec);
        swr_free(&is->swr_ctx);
        av_freep(&is->audio_buf1);
        is->audio_buf1_size = 0;
        is->audio_buf = NULL;

        if (is->rdft) {
            av_tx_uninit(&is->rdft);
            av_freep(&is->real_data);
            av_freep(&is->rdft_data);
            is->rdft = NULL;
            is->rdft_bits = 0;
        }
        break;
    case AVMEDIA_TYPE_VIDEO:
        decoder_abort(&is->viddec, &is->pictq);
        decoder_destroy(&is->viddec);
        break;
    case AVMEDIA_TYPE_SUBTITLE:
        decoder_abort(&is->subdec, &is->subpq);
        decoder_destroy(&is->subdec);
        break;
    default:
        break;
    }

    ic->streams[stream_index]->discard = AVDISCARD_ALL;
    switch (codecpar->codec_type) {
    case AVMEDIA_TYPE_AUDIO:
        is->audio_st = NULL;
        is->audio_stream = -1;
        break;
    case AVMEDIA_TYPE_VIDEO:
        is->video_st = NULL;
        is->video_stream = -1;
        break;
    case AVMEDIA_TYPE_SUBTITLE:
        is->subtitle_st = NULL;
        is->subtitle_stream = -1;
        break;
    default:
        break;
    }
}

static void stream_close(VideoState *is)
{
    /* XXX: use a special url_shutdown call to abort parse cleanly */
    is->abort_request = 1;
    SDL_WaitThread(is->read_tid, NULL);

    /* close each stream */
    if (is->audio_stream >= 0)
        stream_component_close(is, is->audio_stream);
    if (is->video_stream >= 0)
        stream_component_close(is, is->video_stream);
    if (is->subtitle_stream >= 0)
        stream_component_close(is, is->subtitle_stream);

    avformat_close_input(&is->ic);

    packet_queue_destroy(&is->videoq);
    packet_queue_destroy(&is->audioq);
    packet_queue_destroy(&is->subtitleq);

    /* free all pictures */
    frame_queue_destroy(&is->pictq);
    frame_queue_destroy(&is->sampq);
    frame_queue_destroy(&is->subpq);
    SDL_DestroyCond(is->continue_read_thread);
    sws_freeContext(is->sub_convert_ctx);
    av_free(is->filename);
    if (is->vis_texture)
        SDL_DestroyTexture(is->vis_texture);
    if (is->vid_texture)
        SDL_DestroyTexture(is->vid_texture);
    if (is->sub_texture)
        SDL_DestroyTexture(is->sub_texture);
    av_free(is);
}

/* ---- settings file: ~/.config/ffplay-custom/settings.conf ---- */
#include <sys/stat.h>

static double  cfg_seek = 2.0;              /* seconds the Left/Right keys jump */
static int     cfg_vol_step = 2;            /* volume change per Up/Down press */
static int64_t cfg_hide_delay = 4000000;    /* microseconds until bars and cursor hide */
static int     cfg_fullscreen = 1;          /* 1 = open fullscreen */
static int     cfg_bar_r = 84, cfg_bar_g = 120, cfg_bar_b = 168;   /* bar color */
static int     cfg_remember_volume = 1;     /* 1 = remember the volume between runs */
static int     cfg_quit_when_done = 0;      /* 1 = quit when the queue ends */
static int     cfg_wheel = 0;               /* mouse wheel: 0 = off, 1 = volume, 2 = seek */
static int     cfg_crossfade = 0;           /* seconds the end of one item and the start of the next overlap (0 to 10) */
#define cfg_keep_window 1               /* the window keeps the size you gave it from one item to the next (nothing is kept between runs) */
static int     ui_user_sized = 0;           /* 1 = the window was resized or tiled by the user: the next items keep its size */
static int ui_keep_w = 0, ui_keep_h = 0;    /* the size the user gave the window: the next items open at it (full screen never changes it) */
static int ui_prog_w = 0, ui_prog_h = 0;    /* the size we asked for ourselves: an event with this size is ours, not the user's */
static int64_t ui_fs_toggle_at = 0;         /* when the window last went into or out of full screen */
static volatile int64_t ui_seek_last = 0;   /* when a seek was last asked for: the sound is quiet around it */
static int ui_hov_x = -1, ui_hov_y = -1;    /* where the mouse is (for the previews on the tiles) */
static double ui_flow_hint = 0.0;           /* 0 to 1: the "Back to playing" hint */
static int ui_tp_on = 0;                    /* 1 = a tile preview is waiting to start or is playing: keep drawing */
static int64_t ui_prog_until = 0;           /* until then a change of the window size is our own, not the user's */
static float   xf_open_gain = 1.0f;         /* loudness a stream starts with: 0 while it opens under the end of the last item */
static float   ui_sleep_gain = 1.0f;        /* the sleep timer fades everything out with this */
static VideoState *xf_stream = NULL; /* the next item, already playing under the end of this one */
static char   *xf_name = NULL;              /* its name in the queue */
static char   *xf_failed = NULL;            /* an item that would not open early: do not try again */
static unsigned ui_stream_serial = 0;       /* counts the streams opened so far */
static void ui_key_save(FILE *f);
static void ui_key_load(void);
static char    cfg_font[512] = "";          /* font file, empty = the system font */

/* Text written to a new settings file, so there is something to edit */
static const char *settings_default_text =
    "# ffplay-custom settings. Lines starting with # are ignored.\n"
    "# Change a value, save the file, and start ffplay-custom again.\n"
    "\n"
    "# Seconds the Left/Right arrow keys jump\n"
    "seek_seconds = 2\n"
    "\n"
    "# Volume change for each Up/Down press (the scale is 0 to 128)\n"
    "volume_step = 2\n"
    "\n"
    "# Seconds without mouse movement before the bars and cursor hide\n"
    "hide_seconds = 4\n"
    "\n"
    "# 1 = always open fullscreen, 0 = open in a window\n"
    "fullscreen = 1\n"
    "\n"
    "# Color of the filled part of the bars: red green blue (0 to 255 each)\n"
    "bar_color = 84 120 168\n"
    "\n"
    "# 1 = remember the volume between runs, 0 = always start at full volume\n"
    "remember_volume = 1\n"
    "\n"
    "# 1 = quit when the queue ends, 0 = show the idle screen\n"
    "quit_when_done = 0\n"
    "\n"
    "# Mouse wheel (and touchpad swipe): 0 = off, 1 = volume, 2 = seek by the seek step\n"
    "mouse_wheel = 0\n"
    "\n"
    "# Font file for the text (leave empty to use the system font)\n"
    "font =\n";

/* Read the settings file. If there is none yet, write one with the defaults. */
static void settings_load(void)
{
    char path[1024], line[256];
    const char *home = getenv("HOME");
    char *p;
    FILE *f;
    double d;
    int n, r, g, b;

    if (!home)
        return;
    /* Make sure the folders exist (does nothing if they already do) */
    snprintf(path, sizeof(path), "%s/.config", home);
    mkdir(path, 0755);
    snprintf(path, sizeof(path), "%s/.config/ffplay-custom", home);
    mkdir(path, 0755);
    snprintf(path, sizeof(path), "%s/.config/ffplay-custom/settings.conf", home);

    f = fopen(path, "r");
    if (!f) {
        /* No file yet: write the defaults */
        f = fopen(path, "w");
        if (f) {
            fputs(settings_default_text, f);
            fclose(f);
        }
        return;
    }

    while (fgets(line, sizeof(line), f)) {
        /* Let colors be written with commas too */
        for (p = line; *p; p++)
            if (*p == ',')
                *p = ' ';

        if (sscanf(line, " seek_seconds = %lf", &d) == 1)
            cfg_seek = av_clipd(d, 0.1, 600.0);
        else if (sscanf(line, " volume_step = %d", &n) == 1)
            cfg_vol_step = av_clip(n, 1, 32);
        else if (sscanf(line, " hide_seconds = %lf", &d) == 1)
            cfg_hide_delay = (int64_t)(av_clipd(d, 0.5, 3600.0) * 1000000);
        else if (sscanf(line, " fullscreen = %d", &n) == 1)
            cfg_fullscreen = (n != 0);
        else if (sscanf(line, " bar_color = %d %d %d", &r, &g, &b) == 3) {
            cfg_bar_r = av_clip(r, 0, 255);
            cfg_bar_g = av_clip(g, 0, 255);
            cfg_bar_b = av_clip(b, 0, 255);
        } else if (sscanf(line, " remember_volume = %d", &n) == 1)
            cfg_remember_volume = (n != 0);
        else if (sscanf(line, " quit_when_done = %d", &n) == 1)
            cfg_quit_when_done = (n != 0);
        else if (sscanf(line, " mouse_wheel = %d", &n) == 1)
            cfg_wheel = av_clip(n, 0, 2);
        else if (sscanf(line, " crossfade = %d", &n) == 1)
            cfg_crossfade = av_clip(n, 0, 10);
        else if (sscanf(line, " font = %400[^\n]", cfg_font) == 1) {
            n = (int)strlen(cfg_font);
            while (n > 0 && cfg_font[n - 1] == ' ')
                cfg_font[--n] = 0;
        }
    }
    fclose(f);

    is_full_screen = cfg_fullscreen;
}

/* Write all the settings back to the file (the Preferences panel uses this) */
static void settings_save(void)
{
    char path[1024];
    const char *home = getenv("HOME");
    FILE *f;

    if (!home)
        return;
    snprintf(path, sizeof(path), "%s/.config/ffplay-custom/settings.conf", home);
    f = fopen(path, "w");
    if (!f)
        return;
    fprintf(f, "# ffplay-custom settings. Lines starting with # are ignored.\n");
    fprintf(f, "# Change a value, save the file, and start ffplay-custom again.\n\n");
    fprintf(f, "# Seconds the Left/Right arrow keys jump\nseek_seconds = %g\n\n", cfg_seek);
    fprintf(f, "# Volume change for each Up/Down press (the scale is 0 to 128)\nvolume_step = %d\n\n", cfg_vol_step);
    fprintf(f, "# Seconds without mouse movement before the bars and cursor hide\nhide_seconds = %g\n\n",
            cfg_hide_delay / 1000000.0);
    fprintf(f, "# 1 = always open fullscreen, 0 = open in a window\nfullscreen = %d\n\n", cfg_fullscreen);
    fprintf(f, "# Color of the filled part of the bars: red green blue (0 to 255 each)\nbar_color = %d %d %d\n\n",
            cfg_bar_r, cfg_bar_g, cfg_bar_b);
    fprintf(f, "# 1 = remember the volume between runs, 0 = always start at full volume\nremember_volume = %d\n\n",
            cfg_remember_volume);
    fprintf(f, "# 1 = quit when the queue ends, 0 = show the idle screen\nquit_when_done = %d\n\n", cfg_quit_when_done);
    fprintf(f, "# Mouse wheel (and touchpad swipe): 0 = off, 1 = volume, 2 = seek by the seek step\nmouse_wheel = %d\n\n", cfg_wheel);
    fprintf(f, "# Seconds the end of one item and the start of the next overlap (0 = off, 10 at most)\ncrossfade = %d\n\n",
            cfg_crossfade);
    ui_key_save(f);
    fprintf(f, "# Font file for the text (leave empty to use the system font)\nfont = %s\n", cfg_font);
    fclose(f);
}

/* ---- remember the last volume between runs ---- */
#include <sys/stat.h>

/* Builds ~/.config/ffplay-custom/volume. Returns 0 if HOME is not set. */
static int volume_path(char *path, size_t size, int make_dir)
{
    const char *home = getenv("HOME");

    if (!home)
        return 0;
    if (make_dir) {
        snprintf(path, size, "%s/.config/ffplay-custom", home);
        mkdir(path, 0755);
    }
    snprintf(path, size, "%s/.config/ffplay-custom/volume", home);
    return 1;
}

/* Returns the saved volume (0-128), or fallback if there is none */
static int volume_load(int fallback)
{
    char path[1024];
    int v = 0;
    FILE *f;

    if (!cfg_remember_volume || !volume_path(path, sizeof(path), 0))
        return fallback;
    f = fopen(path, "r");
    if (!f)
        return fallback;
    if (fscanf(f, "%d", &v) != 1)
        v = fallback;
    fclose(f);
    return av_clip(v, 0, SDL_MIX_MAXVOLUME);
}

static void volume_save(int volume)
{
    char path[1024];
    FILE *f;

    if (!cfg_remember_volume || !volume_path(path, sizeof(path), 1))
        return;
    f = fopen(path, "w");
    if (!f)
        return;
    fprintf(f, "%d\n", volume);
    fclose(f);
}

static int exit_status = 0;  /* 0 = quit, 10 = next, 11 = previous */

/* ---- the previews on the seek bar ---- */
#define UI_THUMBS 1                     /* 0 = no previews */
#define UI_TH_MAX 240

typedef struct {
    uint8_t *rgba;                      /* the picture, made by the reader */
    int ready;                          /* 1 = rgba is complete */
    SDL_Texture *tex;                   /* made on first use, by the main thread */
} UiThumb;

static struct {
    SDL_Thread *thread;
    volatile int abort;
    int id, n, w, h;                    /* the stream they belong to, how many, the size of each */
    double dur;                         /* seconds */
    int64_t start;                      /* the file's start time, in AV_TIME_BASE units */
    char *file;
    UiThumb t[UI_TH_MAX];
} ui_th;

static int ui_th_intr(void *p)
{
    return *(volatile int *)p;
}

/* The reader: its own copy of the file and a decoder that only decodes key frames */
static int ui_th_run(void *arg)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    const AVCodec *dec = NULL;
    AVPacket *pk = av_packet_alloc();
    AVFrame *fr = av_frame_alloc();
    struct SwsContext *sws = NULL;
    int vs, n = ui_th.n, i, m = 0, stride, order[UI_TH_MAX], tw = ui_th.w, th = ui_th.h, made = 0;
    int64_t t0 = av_gettime_relative();

    SDL_SetThreadPriority(SDL_THREAD_PRIORITY_LOW);      /* in the background: the playing comes first */
    if (!pk || !fr)
        goto end;
    ic = avformat_alloc_context();
    if (!ic)
        goto end;
    ic->interrupt_callback.callback = ui_th_intr;
    ic->interrupt_callback.opaque = (void *)&ui_th.abort;
    if (avformat_open_input(&ic, ui_th.file, NULL, NULL) < 0) {
        ic = NULL;
        goto end;
    }
    if (avformat_find_stream_info(ic, NULL) < 0)
        goto end;
    vs = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, &dec, 0);
    if (vs < 0 || !dec || (ic->streams[vs]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        goto end;
    cc = avcodec_alloc_context3(dec);
    if (!cc || avcodec_parameters_to_context(cc, ic->streams[vs]->codecpar) < 0)
        goto end;
    cc->skip_frame = AVDISCARD_NONKEY;
    cc->thread_count = 1;
    if (avcodec_open2(cc, dec, NULL) < 0)
        goto end;

    for (stride = 32; stride >= 1; stride >>= 1)        /* coarse first, then finer: every time some are ready everywhere */
        for (i = 0; i < n; i += stride)
            if (stride == 32 || (i % (stride << 1)))
                order[m++] = i;

    for (i = 0; i < m && !ui_th.abort; i++) {
        int idx = order[i], got = 0, tries;
        int64_t ts = ui_th.start + (int64_t)((idx + 0.5) * ui_th.dur / n * AV_TIME_BASE);
        uint8_t *dst, *dp[4] = { NULL };
        int dl[4] = { 0 };

        if (av_seek_frame(ic, -1, ts, AVSEEK_FLAG_BACKWARD) < 0)
            continue;
        avcodec_flush_buffers(cc);
        for (tries = 0; tries < 400 && !got && !ui_th.abort; tries++) {
            if (av_read_frame(ic, pk) < 0)
                break;
            if (pk->stream_index == vs && avcodec_send_packet(cc, pk) == 0) {
                if (avcodec_receive_frame(cc, fr) == 0) {
                    got = 1;
                } else {                        /* the decoder keeps the picture back: ask for it */
                    avcodec_send_packet(cc, NULL);
                    if (avcodec_receive_frame(cc, fr) == 0)
                        got = 1;
                    else
                        avcodec_flush_buffers(cc);
                }
            }
            av_packet_unref(pk);
        }
        if (!got)
            continue;
        sws = sws_getCachedContext(sws, fr->width, fr->height, fr->format, tw, th, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
        dst = av_malloc((size_t)tw * th * 4);
        if (sws && dst) {
            dp[0] = dst;
            dl[0] = tw * 4;
            sws_scale(sws, (const uint8_t * const *)fr->data, fr->linesize, 0, fr->height, dp, dl);
            ui_th.t[idx].rgba = dst;
            __atomic_store_n(&ui_th.t[idx].ready, 1, __ATOMIC_RELEASE);
            made++;
        } else {
            av_free(dst);
        }
        av_frame_unref(fr);
        av_usleep(6000);                        /* a breath between pictures: never a whole core */
    }
end:
    av_log(NULL, AV_LOG_VERBOSE, "ffplay-custom: seek previews: %d of %d made in %d ms\n", made, n, (int)((av_gettime_relative() - t0) / 1000));
    sws_freeContext(sws);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    av_packet_free(&pk);
    av_frame_free(&fr);
    return 0;
}

static void ui_th_stop(void)
{
    int i;

    if (ui_th.thread) {
        ui_th.abort = 1;
        SDL_WaitThread(ui_th.thread, NULL);
        ui_th.thread = NULL;
    }
    for (i = 0; i < UI_TH_MAX; i++) {
        if (ui_th.t[i].tex)
            SDL_DestroyTexture(ui_th.t[i].tex);
        ui_th.t[i].tex = NULL;
        av_freep(&ui_th.t[i].rgba);
        ui_th.t[i].ready = 0;
    }
    av_freep(&ui_th.file);
    ui_th.n = 0;
    ui_th.id = 0;
    ui_th.abort = 0;
}

/* A change of the window size has arrived. If it is the user's (not ours, and not full screen going in or out), the next
   items open at this size. Full screen never changes it, so a video can not come back at the size of the whole screen. */
static void ui_note_size(int w, int h)
{
    int64_t now = av_gettime_relative();

    if (!cfg_keep_window || !window || is_full_screen || w < 260 || h < 160)
        return;
    if (SDL_GetWindowFlags(window) & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP))
        return;
    if (now - ui_fs_toggle_at < 1500000)        /* the sizes that go with full screen are the screen's, or the window coming back */
        return;
    if (now < ui_prog_until && FFABS(w - ui_prog_w) <= 2 && FFABS(h - ui_prog_h) <= 2)
        return;                                 /* our own change */
    ui_user_sized = 1;
    ui_keep_w = w;
    ui_keep_h = h;
}

static void do_exit(VideoState *is)
{
    ui_th_stop();
    if (is)
        volume_save(is->audio_volume);
    if (is) {
        stream_close(is);
    }
#if SDL_VERSION_ATLEAST(2, 0, 5)
    if (window && (SDL_GetWindowFlags(window) & SDL_WINDOW_SHOWN)) {
        SDL_SetWindowOpacity(window, 0.0f);     /* the window manager's closing effect then has nothing to show */
        SDL_PumpEvents();
        SDL_Delay(70);
        SDL_HideWindow(window);
    }
#endif
    if (renderer)
        SDL_DestroyRenderer(renderer);
    if (window)
        SDL_DestroyWindow(window);
    uninit_opts();
    av_freep(&vfilters_list);
    avformat_network_deinit();
    if (show_status)
        printf("\n");
    SDL_Quit();
    av_log(NULL, AV_LOG_QUIET, "%s", "");
    exit(exit_status);
}

static void sigterm_handler(int sig)
{
    exit(123);
}

static void set_default_window_size(int width, int height, AVRational sar)
{
    SDL_Rect rect;
    int max_width  = screen_width  ? screen_width  : INT_MAX;
    int max_height = screen_height ? screen_height : INT_MAX;
    if (max_width == INT_MAX && max_height == INT_MAX)
        max_height = height;
    calculate_display_rect(&rect, 0, 0, max_width, max_height, width, height, sar);
    default_width  = rect.w;
    default_height = rect.h;
}

#define UI_BAR_H 28
#define UI_ON(is) ((is)->width >= 260 && (is)->height >= UI_BAR_H * 3)

static int ui_shown_once = 0;   /* the window is shown once; later items leave its place and workspace alone */

static int video_open(VideoState *is)
{
    int w,h;

    w = screen_width ? screen_width : default_width;
    h = screen_height ? screen_height : default_height;

    if (!window_title)
        window_title = input_filename;
    SDL_SetWindowTitle(window, window_title);

    {
        int tiled = 0, cw = 0, ch = 0;
        SDL_Rect ub;

        if (ui_shown_once && !is_full_screen && SDL_GetDisplayUsableBounds(SDL_GetWindowDisplayIndex(window), &ub) == 0) {
            SDL_GetWindowSize(window, &cw, &ch);
            tiled = ch >= ub.h - 8 || cw >= ub.w - 8;       /* maximized or tiled by the window manager: its size stays */
        }
        if (tiled) {
            w = cw;
            h = ch;
        } else {
            ui_prog_until = av_gettime_relative() + 1500000;     /* the size change that follows is ours */
            ui_prog_w = w;
            ui_prog_h = h;
            SDL_SetWindowSize(window, w, h);
        }
        if (!ui_shown_once)
            SDL_SetWindowPosition(window, screen_left, screen_top);
        if (is_full_screen)
            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);
        if (!ui_shown_once) {
            SDL_ShowWindow(window);         /* only the first time: showing it again would raise it, even from another workspace */
            ui_shown_once = 1;
        }
    }

    is->width  = w;
    is->height = h;

    return 0;
}

/* ---- minimal bottom UI: seek bar + volume bar ---- */
#include "libavutil/xga_font_data.h"

static double get_master_clock(VideoState *is);
static void stream_seek(VideoState *is, int64_t pos, int64_t rel, int by_bytes);
#define UI_PRECISE_SEEK 1                /* 0 = seek to the nearest key frame, as before */
static int ui_precise_next = 0;         /* 1 = the next seek must land exactly on its time */

static int ui_hover = 0;   /* 1 = mouse is over the bar strip */
static int ui_drag = 0;               /* 0 = none, 1 = seek bar, 2 = volume bar */
static double ui_seek_frac = 0.0;
static int64_t ui_hold_until = 0;

/* ----- light glass: on the frosted glass, text and lines that were light are drawn dark instead -----
   ui_ink_dark is 1 while a panel on glass is drawn. Light grays and white then turn dark (the lighter they were, the
   darker they become); colors, such as your bar color, stay as they are. */
static int ui_ink_dark = 0;

static void ui_ink(int *r, int *g, int *b)
{
    if (ui_ink_dark && FFMIN3(*r, *g, *b) >= 100 && FFMAX3(*r, *g, *b) - FFMIN3(*r, *g, *b) <= 40) {
        *r = (255 - *r) * 8 / 10;
        *g = (255 - *g) * 8 / 10;
        *b = (255 - *b) * 8 / 10;
    }
}

static int ui_set_color(SDL_Renderer *rd, int r, int g, int b, int a)
{
    ui_ink(&r, &g, &b);
    return (SDL_SetRenderDrawColor)(rd, r, g, b, a);
}
#define SDL_SetRenderDrawColor(rd, r, g, b, a) ui_set_color(rd, r, g, b, a)

/* ---- showing the picture without waiting for the window manager ----
   A window that is not on screen (another workspace, the Multitasking view) can have its frames held back for a long
   time. Waiting for them stops the main loop, so pictures pile up, the reader stops reading sound too, and playback
   stutters until the window is seen again. So a present that takes long switches vsync off; it comes back as soon as
   the window is seen again. */
static int ui_vsync_on = 1;
static int ui_present_slow = 0;

static void ui_vsync_set(int on)
{
#if SDL_VERSION_ATLEAST(2, 0, 18)
    if (renderer && on != ui_vsync_on) {
        SDL_RenderSetVSync(renderer, on);
        ui_vsync_on = on;
    }
#endif
    ui_present_slow = 0;
}

static void ui_present(void)
{
    int64_t t0 = av_gettime_relative(), dt;

    SDL_RenderPresent(renderer);
    dt = av_gettime_relative() - t0;
    if (dt > 100000) {
        if (ui_vsync_on)
            av_log(NULL, AV_LOG_WARNING, "ffplay-custom: the window manager held a frame for %d ms (window in the background?): not waiting for the screen until the window is seen again\n", (int)(dt / 1000));
        ui_vsync_set(0);
    }
}

/* Is the window out of sight for sure (minimized or hidden)? Then nothing is drawn. */
static int ui_win_unseen(void)
{
    static int was = 0;
    int now = window && (SDL_GetWindowFlags(window) & (SDL_WINDOW_MINIMIZED | SDL_WINDOW_HIDDEN));

    if (now != was) {
        was = now;
        av_log(NULL, AV_LOG_WARNING, "ffplay-custom: window %s\n", now ? "hidden or minimized: not drawing, the pictures still go by" : "on screen again");
    }
    return now;
}

/* Show the cursor and bar again and restart the hide timer */
static void ui_wake(void)
{
    if (!ui_vsync_on)
        ui_vsync_set(1);                /* the mouse moved: the window is in sight again */
    if (cursor_hidden) {
        SDL_ShowCursor(1);
        cursor_hidden = 0;
    }
    cursor_last_shown = av_gettime_relative();
}

static void ui_layout(VideoState *is, SDL_Rect *sk, SDL_Rect *vo)
{
    /* Floating rounded pill style with 16px bottom margin and side padding */
    int margin_x = 24;
    int bottom_offset = 6;
    int bar_h = 8;
    int ty = is->height - bottom_offset - bar_h;

    vo->w = 90;
    vo->h = bar_h;
    vo->y = ty;
    vo->x = is->width - margin_x - 40 - vo->w;
    sk->x = margin_x + 28;                  /* room for the previous button on the left */
    sk->y = ty;
    sk->h = bar_h;
    sk->w = vo->x - 104 - sk->x;            /* room for next, shuffle and repeat on the right */
}

static void ui_text(int x, int y, const char *s)
{
    for (; *s; s++, x += 8) {
        const uint8_t *g = avpriv_vga16_font + (uint8_t)*s * 16;
        for (int row = 0; row < 16; row++)
            for (int col = 0; col < 8; col++)
                if (g[row] & (0x80 >> col))
                    SDL_RenderDrawPoint(renderer, x + col, y + row);
    }
}

/* Fill a rectangle with fully rounded ends, using the current draw color.
   Each row is a 1px tall rectangle, shortened at the ends to follow a circle. */
static void ui_pill(const SDL_Rect *t)
{
    double rad = t->h / 2.0;
    int row;

    for (row = 0; row < t->h; row++) {
        double dy = row + 0.5 - rad;                      /* row center to bar center */
        int inset = (int)(rad - sqrt(rad * rad - dy * dy) + 0.5);
        SDL_Rect line = { t->x + inset, t->y + row, t->w - 2 * inset, 1 };

        if (line.w > 0)
            SDL_RenderFillRect(renderer, &line);
    }
}

static void ui_bar(SDL_Rect *t, double frac)
{
    SDL_Rect fill = *t;

    frac = av_clipd(frac, 0.0, 1.0);
    fill.w = (int)(t->w * frac);
    if (fill.w < t->h)
        fill.w = t->h;      /* keep at least one full round end */

    /* Track: faint white pill */
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 45);
    ui_pill(t);

    /* Progress / volume: soft muted blue (the numbers are red, green, blue, opacity) */
    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 200);
    ui_pill(&fill);
}

static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a);
static double ui_fade = 1.0;        /* 0 to 1: everything drawn through the helpers below is this strong */

static int ui_shadows_on = 0;       /* 1 = black shadows under panels, floating text, the volume number and the covers; 0 = none */

/* Text with a soft shadow under it, for text that floats over the picture without a box */
static void ui_label_s(int x, int cy, const char *s, int px, int r, int g, int b, int a)
{
    if (ui_shadows_on)
        ui_label(x + 1, cy + 2, s, px, 0, 0, 0, a * 150 / 255);
    ui_label(x, cy, s, px, r, g, b, a);
}

/* ---- chapters on the seek bar and the seek bar tooltip ---- */
static int ui_hover_x = -1;         /* mouse x while it is over the bar strip */

static int ui_text_width(const char *s, int px);

/* Start of chapter i, in seconds from the start of the file */
static double ui_chapter_start(VideoState *is, unsigned i)
{
    AVChapter *ch = is->ic->chapters[i];
    double s = ch->start * av_q2d(ch->time_base);

    if (is->ic->start_time != AV_NOPTS_VALUE)
        s -= is->ic->start_time / (double)AV_TIME_BASE;
    return s;
}

/* The seek bar. A file with chapters gets a bar in sections: a small gap where each chapter starts,
   and the section under the mouse is a little brighter. Without chapters it is the plain bar. */
static void ui_seek_bar(VideoState *is, SDL_Rect *sk, double frac)
{
    double dur = is->ic->duration / (double)AV_TIME_BASE, f;
    int xs[130], n = 1, i, gap = 4, fx, hx = -1, ax, bx, x;
    unsigned c;
    SDL_Rect seg, fill;

    if (dur <= 0 || is->ic->nb_chapters < 2) {
        ui_bar(sk, frac);
        return;
    }
    xs[0] = sk->x;
    for (c = 1; c < is->ic->nb_chapters && n < 126; c++) {      /* where each chapter after the first starts */
        f = ui_chapter_start(is, c) / dur;
        if (f <= 0.004 || f >= 0.996)
            continue;
        x = sk->x + (int)(f * sk->w);
        if (x - xs[n - 1] < 12 || sk->x + sk->w - x < 12)       /* too close to the last one or the end */
            continue;
        xs[n++] = x;
    }
    xs[n] = sk->x + sk->w;
    if (n < 2) {
        ui_bar(sk, frac);
        return;
    }
    fx = sk->x + (int)(av_clipd(frac, 0.0, 1.0) * sk->w);
    if (ui_drag == 1)
        hx = sk->x + (int)(ui_seek_frac * sk->w);
    else if (ui_hover && ui_hover_x >= sk->x - 6 && ui_hover_x <= sk->x + sk->w + 6)
        hx = ui_hover_x;

    for (i = 0; i < n; i++) {
        ax = xs[i] + (i ? gap / 2 : 0);
        bx = xs[i + 1] - (i < n - 1 ? gap - gap / 2 : 0);
        seg.x = ax;
        seg.y = sk->y;
        seg.w = bx - ax;
        seg.h = sk->h;
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, (hx >= xs[i] && hx < xs[i + 1]) ? 80 : 45);
        ui_pill(&seg);
        if (fx > ax) {                          /* how far the playing has got inside this section */
            fill = seg;
            fill.w = FFMAX(FFMIN(fx, bx) - ax, FFMIN(seg.h, seg.w));
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 200);
            ui_pill(&fill);
        }
    }
}

/* Start the previews of the stream that plays, once it has played for a moment (a second reader should not compete with the opening) */
static void ui_th_tick(VideoState *is)
{
    static int next_id = 0;
    double pos, dur;
    int cw, ch, tw, th;

    if (!UI_THUMBS || is->ui_thumb_id || !is->ic)
        return;
    pos = get_master_clock(is);
    if (isnan(pos) || pos < 4.0)                /* not in the first seconds of an item */
        return;
    dur = is->ic->duration / (double)AV_TIME_BASE;
    if (!is->video_st || (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) || dur < 8.0 || !is->filename ||
        strstr(is->filename, "://") || !is->video_st->codecpar->width || !is->video_st->codecpar->height) {
        is->ui_thumb_id = -1;                   /* songs, short clips and streams get none */
        ui_th_stop();
        return;
    }
    cw = is->video_st->codecpar->width;
    ch = is->video_st->codecpar->height;
    tw = 192;
    th = (int)((double)ch * tw / cw);
    if (th > 108) {
        th = 108;
        tw = (int)((double)cw * th / ch);
    }
    tw = FFMAX(tw & ~1, 16);
    th = FFMAX(th & ~1, 16);
    ui_th_stop();                               /* the ones of the item before */
    is->ui_thumb_id = ++next_id;
    ui_th.id = is->ui_thumb_id;
    ui_th.n = av_clip((int)(dur / 3.0), 40, UI_TH_MAX);
    ui_th.w = tw;
    ui_th.h = th;
    ui_th.dur = dur;
    ui_th.start = is->ic->start_time != AV_NOPTS_VALUE ? is->ic->start_time : 0;
    ui_th.file = av_strdup(is->filename);
    if (!ui_th.file || !(ui_th.thread = SDL_CreateThread(ui_th_run, "seek previews", NULL))) {
        ui_th_stop();
        is->ui_thumb_id = -1;
    }
}

/* The preview for the fraction f of the video, above the time label (its top is at ybox), centered on cx. It takes the nearest
   one that is ready, so it never waits; a few more are ready every moment */
static void ui_th_draw(VideoState *is, double f, int cx, int ybox)
{
    int n = ui_th.n, idx, d, found = -1;
    SDL_Rect r, sh;
    UiThumb *t;
    double sc;

    if (!UI_THUMBS || ui_th.id <= 0 || ui_th.id != is->ui_thumb_id || n <= 0 || is->width < 380)
        return;
    idx = av_clip((int)(f * n), 0, n - 1);
    for (d = 0; d < n && found < 0; d++) {
        if (idx - d >= 0 && __atomic_load_n(&ui_th.t[idx - d].ready, __ATOMIC_ACQUIRE))
            found = idx - d;
        else if (idx + d < n && __atomic_load_n(&ui_th.t[idx + d].ready, __ATOMIC_ACQUIRE))
            found = idx + d;
    }
    if (found < 0)
        return;
    t = &ui_th.t[found];
    if (!t->tex) {
        t->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ui_th.w, ui_th.h);
        if (!t->tex)
            return;
        SDL_UpdateTexture(t->tex, NULL, t->rgba, ui_th.w * 4);
        SDL_SetTextureBlendMode(t->tex, SDL_BLENDMODE_NONE);
    }
    sc = is->width >= 1400 ? 1.5 : is->width >= 900 ? 1.25 : 1.0;
    r.w = (int)(ui_th.w * sc);
    r.h = (int)(ui_th.h * sc);
    r.x = av_clip(cx - r.w / 2, 8, FFMAX(is->width - r.w - 8, 8));
    r.y = ybox - 6 - r.h;
    if (r.y < 34)
        return;                                 /* no room above the bar in a small window */
    sh.x = r.x - 3;
    sh.y = r.y - 3;
    sh.w = r.w + 6;
    sh.h = r.h + 6;
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 90);
    SDL_RenderFillRect(renderer, &sh);
    SDL_RenderCopy(renderer, t->tex, NULL, &r);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 60);
    SDL_RenderDrawRect(renderer, &r);
}

/* A small label above the seek bar: the time under the mouse (or where you are dragging to),
   with the title of the chapter that time belongs to, if the file has chapters */
static void ui_seek_tooltip(VideoState *is, const SDL_Rect *sk)
{
    double dur = is->ic->duration / (double)AV_TIME_BASE, f, t;
    char text[240], clock[32], title[96] = "";
    AVDictionaryEntry *e;
    unsigned i, found = 0;
    SDL_Rect box;
    int w, cx, s;

    if (dur <= 0)
        return;
    if (ui_drag == 1)
        f = ui_seek_frac;
    else if (ui_hover && ui_hover_x >= sk->x - 6 && ui_hover_x <= sk->x + sk->w + 6)
        f = av_clipd((ui_hover_x - sk->x) / (double)sk->w, 0.0, 1.0);
    else
        return;
    t = f * dur;
    s = (int)t;
    if (s >= 3600)
        snprintf(clock, sizeof(clock), "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60);
    else
        snprintf(clock, sizeof(clock), "%d:%02d", s / 60, s % 60);
    for (i = 0; i < is->ic->nb_chapters; i++)       /* the last chapter that started before this time */
        if (ui_chapter_start(is, i) <= t + 0.001)
            found = i + 1;
    if (found) {
        e = av_dict_get(is->ic->chapters[found - 1]->metadata, "title", NULL, 0);
        if (e)
            snprintf(title, sizeof(title), "%.90s", e->value);
    }
    if (title[0])
        snprintf(text, sizeof(text), "%s   %s", title, clock);
    else
        snprintf(text, sizeof(text), "%s", clock);

    w = ui_text_width(text, 16) + 28;
    cx = av_clip(sk->x + (int)(f * sk->w), w / 2 + 8, FFMAX(is->width - w / 2 - 8, w / 2 + 8));
    box.w = w;
    box.h = 28;
    box.x = cx - w / 2;
    box.y = sk->y - 16 - box.h;
    ui_th_draw(is, f, cx, box.y);
    ui_label_s(box.x + 14, box.y + box.h / 2, text, 16, 245, 245, 245, 255);
}

static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk);
static void ui_titlebar_draw(VideoState *is);

static int ui_on_top = 0;               /* 1 = the window stays above the others */

static void ui_toggle_on_top(void)
{
#if SDL_VERSION_ATLEAST(2, 0, 16)
    if (!window)
        return;
    ui_on_top = !ui_on_top;
    SDL_SetWindowAlwaysOnTop(window, ui_on_top ? SDL_TRUE : SDL_FALSE);
    ui_wake();                          /* the title bar shows, with its dot */
#endif
}

/* Seeking with the keys or the wheel: the bar follows every step at once, and a seek is sent as soon as the one before it has
   shown its picture, so pictures keep coming while a key is held */
static int ui_ks_want = 0;              /* 1 = a seek to ui_ks_target is waiting to be sent */
static double ui_ks_target = 0.0;       /* seconds: where the steps have taken it (the last one sent, when none waits) */
static int64_t ui_ks_next = 0, ui_ks_issued = 0;
static VideoState *ui_ks_is = NULL;     /* the stream the waiting seek is for (a new item cancels it) */

static void ui_draw(VideoState *is)
{
    SDL_Rect sk, vo;
    double frac = 0.0, vfrac;
    char buf[8];

    if (cursor_hidden) return;                  /* the bar hides after the hide delay, paused or not */

    if (!UI_ON(is) || !is->ic)
        return;
    ui_layout(is, &sk, &vo);

    if (is->ic->duration > 0) {
        double pos = get_master_clock(is);
        static double ui_last_pos = 0.0;

        /* While a seek is under way the clock is not valid yet: show where the seek is
           going (or the last known position), so the bar does not jump back to the start */
        if (!seek_by_bytes && ui_ks_want)
            pos = ui_ks_target;                 /* the steps of the keys, before they are sent */
        else if (!seek_by_bytes && is->seek_req)
            pos = is->seek_pos / (double)AV_TIME_BASE;
        else if (isnan(pos))
            pos = (!seek_by_bytes && is->seek_pos) ? is->seek_pos / (double)AV_TIME_BASE : ui_last_pos;
        else
            ui_last_pos = pos;
        if (!isnan(pos)) {
            if (is->ic->start_time != AV_NOPTS_VALUE)
                pos -= is->ic->start_time / (double)AV_TIME_BASE;
            frac = av_clipd(pos / (is->ic->duration / (double)AV_TIME_BASE), 0.0, 1.0);
        }
    }
    if (ui_drag == 1 || av_gettime_relative() < ui_hold_until)
        frac = ui_seek_frac;
    vfrac = is->muted ? 0.0 : is->audio_volume / (double)SDL_MIX_MAXVOLUME;

    /* No background panel: the bars float directly over the video */
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);

    {                                           /* a dark glass strip as small as it can be: the bars stay visible on any picture */
        SDL_Rect row;
        int y, top = sk.y - 12, a;

        row.x = 0;
        row.w = is->width;
        row.h = 1;
        for (y = top - 10; y < is->height; y++) {
            a = y < top ? 125 * (y - (top - 10)) / 10 : 125;
            row.y = y;
            SDL_SetRenderDrawColor(renderer, 0, 0, 0, a);
            SDL_RenderFillRect(renderer, &row);
        }
    }
    ui_seek_bar(is, &sk, frac);
    ui_ctrl_draw(is, &sk);
    ui_bar(&vo, vfrac);

    snprintf(buf, sizeof(buf), "%d", is->muted ? 0 : is->audio_volume);
    /* soft shadow first, then the number */
    if (ui_shadows_on)
        ui_label(vo.x + vo.w + 11, vo.y + vo.h / 2 + 1, buf, 15, 0, 0, 0, 150);
    ui_label(vo.x + vo.w + 10, vo.y + vo.h / 2, buf, 15, 235, 235, 235, 230);
    ui_seek_tooltip(is, &sk);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

static int ui_seek_want = 0;            /* 1 = a seek to ui_seek_frac is waiting to be sent */
static int64_t ui_seek_next = 0;        /* earliest time for the next seek while dragging */

/* Send the waiting seek if the player is ready for it. While dragging, seeks are spaced out
   so each one has time to show a picture. force = the last one: it is not held back. */
static void ui_seek_flush(VideoState *is, int force)
{
    int64_t now = av_gettime_relative();

    if (!ui_seek_want || is->seek_req)
        return;
    if (!force && now < ui_seek_next)
        return;
    ui_seek_want = 0;
    ui_seek_next = now + 50000;         /* about 20 seeks a second while dragging */
    if (seek_by_bytes || is->ic->duration <= 0) {
        int64_t size = avio_size(is->ic->pb);

        if (size > 0)
            stream_seek(is, (int64_t)(size * ui_seek_frac), 0, 1);
    } else {
        int64_t ts = (int64_t)(ui_seek_frac * is->ic->duration);

        if (is->ic->start_time != AV_NOPTS_VALUE)
            ts += is->ic->start_time;
        ui_precise_next = force;        /* the last seek of a drag lands exactly */
        stream_seek(is, ts, 0, 0);
    }
}

/* Send the waiting key seek when the one before it has landed (its picture and its sound are there) */
static void ui_ks_tick(VideoState *is)
{
    int64_t now;

    if (!ui_ks_want)
        return;
    if (!is || !is->ic || is != ui_ks_is) {
        ui_ks_want = 0;
        return;
    }
    now = av_gettime_relative();
    if (now < ui_ks_next)
        return;
    if ((is->seek_req || is->prec_v || is->prec_a) && now - ui_ks_issued < 1500000)
        return;                         /* still on its way: more steps add up meanwhile */
    ui_precise_next = 1;
    stream_seek(is, (int64_t)(ui_ks_target * AV_TIME_BASE), 0, 0);
    ui_ks_issued = now;
    ui_ks_next = now + 30000;
    ui_ks_want = 0;
}

static void ui_apply(VideoState *is, int x, int final)
{
    SDL_Rect sk, vo;
    double f;

    ui_layout(is, &sk, &vo);
    if (ui_drag == 1) {
        f = av_clipd((x - sk.x) / (double)sk.w, 0.0, 1.0);
        ui_seek_frac = f;
        ui_seek_want = 1;               /* seek to the mouse position as soon as the player can */
        if (final)
            ui_hold_until = av_gettime_relative() + 500000;
        ui_seek_flush(is, final);
    } else if (ui_drag == 2) {
        f = av_clipd((x - vo.x) / (double)vo.w, 0.0, 1.0);
        is->audio_volume = av_clip((int)(f * SDL_MIX_MAXVOLUME / cfg_vol_step + 0.5) * cfg_vol_step,
                                   0, SDL_MIX_MAXVOLUME);
        if (is->audio_volume > 0)
            is->muted = 0;
    }
    is->force_refresh = 1;
}

/* returns 1 if the event was used by the UI strip */
static int ui_flow_click(VideoState *is, int x, int y);
static int ui_flow_motion(VideoState *is, int x, int y);
static int ui_flow_release(VideoState *is, int x, int y);
static int ui_flow_snap_back(VideoState *is);
static int ui_ctrl_click(VideoState *is, int x);

static int ui_mouse(VideoState *is, SDL_Event *ev)
{
    SDL_Rect sk, vo;
    int x;

    if (!UI_ON(is))
        return 0;
    ui_layout(is, &sk, &vo);

    if (cursor_hidden) {
        SDL_ShowCursor(1);
        cursor_hidden = 0;
    }
    cursor_last_shown = av_gettime_relative();

    if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button == SDL_BUTTON_LEFT && ui_flow_click(is, ev->button.x, ev->button.y))
            return 1;                       /* a click on a cover */
        if (ev->button.button == SDL_BUTTON_LEFT && ev->button.y < is->height - UI_BAR_H && ui_flow_snap_back(is))
            return 1;                       /* a tap outside the tiles: the row glides back to the playing item */
        if (ev->button.button != SDL_BUTTON_LEFT || ev->button.y < is->height - UI_BAR_H)
            return 0;
        x = ev->button.x;
        if (ui_ctrl_click(is, x))
            return 1;                       /* previous, next, shuffle or repeat */
        if (x >= vo.x - 10 && x <= vo.x + vo.w + 10)
            ui_drag = 2;
        else if (x >= sk.x - 10 && x <= sk.x + sk.w + 10)
            ui_drag = 1;
        else
            ui_drag = 0;
        if (ui_drag)
            ui_apply(is, x, 0);
        return 1;
    }
    if (ev->type == SDL_MOUSEMOTION) {
        if (ui_flow_motion(is, ev->motion.x, ev->motion.y))
            return 1;                       /* dragging a cover */
        ui_hover = ev->motion.y >= is->height - UI_BAR_H;
        ui_hover_x = ui_hover ? ev->motion.x : -1;
        if (!ui_drag)
            return 0;
        ui_apply(is, ev->motion.x, 0);
        return 1;
    }
    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT &&
        ui_flow_release(is, ev->button.x, ev->button.y))
        return 1;                           /* a click on a cover ends, or a drag drops */
    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT && ui_drag) {
        ui_apply(is, ev->button.x, 1);
        ui_drag = 0;
        return 1;
    }
    return 0;
}

static void ui_menu_draw(void);

/* ---- play queue, other launches, file dialogs and the menu ---- */
#include <dirent.h>
#include <SDL_syswm.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#include <ctype.h>

/* ----- the play queue ----- */
static char **q_items = NULL;   /* paths (or URLs) in the queue */
static int q_count = 0;         /* how many items are in the queue */
static int q_pos = -1;          /* index of the item playing now (-1 = none yet) */
static int q_step = 1;          /* where to go when it ends: 1 = next, -1 = previous */
static int ui_session_volume = -1;  /* volume to keep from one item to the next */

static unsigned char *q_played = NULL;  /* 1 = this item has played */
static int *q_seq = NULL;               /* number of the item in the order it was added (the original order) */
static int q_seq_next = 0;
static int q_shuffle = 0;               /* 1 = shuffle is on */
static int q_forced = -1;               /* an item the user clicked: it plays next */
static char **q_buried = NULL;          /* names of removed items that were playing */
static int q_buried_n = 0;
static int q_cap = 0;                   /* room in all three queue arrays */
static char *q_sleep_item = NULL;       /* stop after this item has played (a pointer into q_items) */
static int q_hold = 0;                  /* 1 = playback stopped for the sleep timer: wait on the idle screen */
static int64_t q_sleep_end = 0;         /* when the sleep timer runs out (0 = no timer) */
static int ui_sleep_sel = 0;            /* the timer choice: 0 off, 1 end of track, 2 to 5 = 5, 10, 30, 60 minutes */
static int ui_user_skip = 0;            /* 1 = the item was ended by the user (n, p, a click), not by reaching its end */

static void queue_seed(void)
{
    static int seeded = 0;

    if (!seeded) {
        srand((unsigned)av_gettime());
        seeded = 1;
    }
}

/* A stream that is ending may still read the name of the item it plays, so the name of a removed
   playing item is kept until no stream is running (queue_reap, called once a stream has closed). */
static void queue_bury(char *name)
{
    char **list = av_realloc_array(q_buried, q_buried_n + 1, sizeof(*q_buried));

    if (!list)
        return;                         /* no memory: the name is simply never freed, which is safe */
    q_buried = list;
    q_buried[q_buried_n++] = name;
}

static void queue_reap(void)
{
    while (q_buried_n > 0)
        av_free(q_buried[--q_buried_n]);
}

/* Make room for `need` items in all three queue arrays. Each array only ever grows, so every one
   always has room for at least q_cap items, even if a later allocation fails. */
static int queue_reserve(int need)
{
    char **items;
    unsigned char *played;
    int *seq, cap;

    if (need <= q_cap)
        return 1;
    cap = FFMAX(need, FFMAX(q_cap * 2, 64));
    items = av_realloc_array(q_items, cap, sizeof(*q_items));
    if (!items)
        return 0;
    q_items = items;
    played = av_realloc(q_played, cap);
    if (!played)
        return 0;
    q_played = played;
    seq = av_realloc_array(q_seq, cap, sizeof(*q_seq));
    if (!seq)
        return 0;
    q_seq = seq;
    q_cap = cap;
    return 1;
}


/* ----- how long each item is: found in the background, for the counter in the queue panel ----- */
typedef struct QDur {
    char *path;
    double secs;
} QDur;
static QDur *q_dur = NULL;                  /* what is known so far */
static int q_dur_n = 0, q_dur_cap = 0;
static char **q_todo = NULL;                /* paths still to look at */
static int q_todo_n = 0, q_todo_head = 0, q_todo_cap = 0;
static SDL_mutex *q_dur_mu = NULL;
static SDL_cond *q_dur_cv = NULL;
static volatile int q_dur_gen = 0;          /* goes up every time a file length is found */

static double queue_probe(const char *path)
{
    AVFormatContext *ic = NULL;
    AVDictionary *opts = NULL;
    double secs = 0;

    if (strstr(path, "://"))
        return 0;                           /* a stream: no length */
    av_dict_set(&opts, "probesize", "1000000", 0);
    av_dict_set(&opts, "analyzeduration", "1000000", 0);
    if (avformat_open_input(&ic, path, NULL, &opts) == 0) {
        avformat_find_stream_info(ic, NULL);
        if (ic->duration > 0)
            secs = ic->duration / (double)AV_TIME_BASE;
        avformat_close_input(&ic);
    }
    av_dict_free(&opts);
    return secs;
}

static int queue_probe_thread(void *arg)
{
    QDur *grown;
    char *path;
    double secs;

    for (;;) {
        SDL_LockMutex(q_dur_mu);
        while (q_todo_head >= q_todo_n)
            SDL_CondWait(q_dur_cv, q_dur_mu);
        path = q_todo[q_todo_head++];
        if (q_todo_head >= q_todo_n)
            q_todo_head = q_todo_n = 0;
        SDL_UnlockMutex(q_dur_mu);

        secs = queue_probe(path);

        SDL_LockMutex(q_dur_mu);
        if (q_dur_n + 1 > q_dur_cap) {
            grown = av_realloc_array(q_dur, FFMAX(q_dur_cap * 2, 64), sizeof(*q_dur));
            if (grown) {
                q_dur = grown;
                q_dur_cap = FFMAX(q_dur_cap * 2, 64);
            }
        }
        if (q_dur_n + 1 <= q_dur_cap) {
            q_dur[q_dur_n].path = path;
            q_dur[q_dur_n].secs = secs;
            q_dur_n++;
            q_dur_gen++;
        } else {
            av_free(path);
        }
        SDL_UnlockMutex(q_dur_mu);
    }
    return 0;
}

/* The length of an item is wanted: look at the file in the background (once per file name) */
static void queue_probe_add(const char *path)
{
    SDL_Thread *t;
    char **grown;
    char *copy;
    int i;

    if (!q_dur_mu) {
        q_dur_mu = SDL_CreateMutex();
        q_dur_cv = SDL_CreateCond();
        if (!q_dur_mu || !q_dur_cv)
            return;
        t = SDL_CreateThread(queue_probe_thread, "item lengths", NULL);
        if (!t)
            return;
        SDL_DetachThread(t);
    }
    copy = av_strdup(path);
    if (!copy)
        return;
    SDL_LockMutex(q_dur_mu);
    for (i = 0; i < q_dur_n; i++)
        if (!strcmp(q_dur[i].path, path))
            goto skip;
    for (i = q_todo_head; i < q_todo_n; i++)
        if (!strcmp(q_todo[i], path))
            goto skip;
    if (q_todo_n + 1 > q_todo_cap) {
        grown = av_realloc_array(q_todo, FFMAX(q_todo_cap * 2, 64), sizeof(*q_todo));
        if (!grown)
            goto skip;
        q_todo = grown;
        q_todo_cap = FFMAX(q_todo_cap * 2, 64);
    }
    q_todo[q_todo_n++] = copy;
    SDL_CondSignal(q_dur_cv);
    SDL_UnlockMutex(q_dur_mu);
    return;
skip:
    SDL_UnlockMutex(q_dur_mu);
    av_free(copy);
}

/* Add up the queue. before = the items that played before the current one, total = all of them,
   unknown = items whose length has not been found yet. streaming = 0 on the idle screen: then
   the item that played last counts as played too. */
static void queue_stats(int streaming, double *before, double *total, int *unknown)
{
    double b = 0, t = 0, s;
    int i, j, miss = 0;

    if (q_dur_mu)
        SDL_LockMutex(q_dur_mu);
    for (i = 0; i < q_count; i++) {
        int found = 0;

        s = 0;
        for (j = 0; q_dur_mu && j < q_dur_n; j++)
            if (!strcmp(q_dur[j].path, q_items[i])) {
                s = q_dur[j].secs;
                found = 1;
                break;
            }
        if (!found)
            miss++;
        t += s;
        if (q_played[i] && (i != q_pos || !streaming))
            b += s;
    }
    if (q_dur_mu)
        SDL_UnlockMutex(q_dur_mu);
    *before = b;
    *total = t;
    *unknown = miss;
}

static void queue_add(const char *path)
{
    unsigned char tmp_played;
    int tmp_seq, lo, j;
    char *name, *tmp_item;

    if (!queue_reserve(q_count + 1))
        return;
    name = av_strdup(path);
    if (!name)
        return;
    q_items[q_count] = name;
    q_played[q_count] = 0;
    q_seq[q_count] = q_seq_next++;
    q_count++;
    queue_probe_add(name);

    if (q_shuffle && q_count > 1) {     /* shuffle is on: the new item lands among the ones still to play */
        queue_seed();
        lo = FFMAX(q_pos + 1, 0);
        j = lo + rand() % (q_count - lo);
        tmp_item = q_items[j];
        tmp_played = q_played[j];
        tmp_seq = q_seq[j];
        q_items[j] = q_items[q_count - 1];
        q_played[j] = q_played[q_count - 1];
        q_seq[j] = q_seq[q_count - 1];
        q_items[q_count - 1] = tmp_item;
        q_played[q_count - 1] = tmp_played;
        q_seq[q_count - 1] = tmp_seq;
    }
}

/* Empty the queue. The next item played will be the first one added after this. */
static void queue_clear(void)
{
    int i;

    for (i = 0; i < q_count; i++) {
        if (i == q_pos)
            queue_bury(q_items[i]);     /* the stream that is ending may still read its name */
        else
            av_free(q_items[i]);
    }
    q_count = 0;
    q_pos = -1;
    q_step = 1;
    q_forced = -1;
    q_seq_next = 0;
    q_sleep_item = NULL;
    q_hold = 0;
    xf_name = NULL;
}

/* Which item plays next? q_count means there is none. */
static int q_repeat = 0;        /* 0 = off, 1 = repeat the queue, 2 = repeat the item playing */
static int q_user_ended = 0;    /* 1 = the item that just ended was ended by the user, not by reaching its end */

static int queue_next(void)
{
    int n;

    if (q_forced >= 0 && q_forced < q_count)
        return q_forced;                        /* the user clicked an item */
    if (q_repeat == 2 && !q_user_ended && q_pos >= 0 && q_pos < q_count)
        return q_pos;                           /* repeat one: play it again */
    n = FFMAX(q_pos + q_step, 0);               /* previous on the first item replays it */
    if (q_repeat == 1 && q_step > 0 && n >= q_count && q_count > 0)
        n = 0;                                  /* repeat all: back to the top */
    return n;
}

struct QPair {
    char *item;
    int seq;
};

static int queue_pair_cmp(const void *a, const void *b)
{
    return ((const struct QPair *)a)->seq - ((const struct QPair *)b)->seq;
}

/* Put the items that have not played yet in a new order: shuffle = at random (always different
   from the order before), otherwise the order they were added in (the original order).
   Items before the playing one stay where they are. Items that already played are kept out of the
   reordered part: they sit just above the playing item, so they do not come back. */
static void queue_reorder(int shuffle)
{
    char **items = NULL;
    unsigned char *flags = NULL;
    int *seqs = NULL;
    struct QPair *pairs = NULL, *orig = NULL, t;
    int pos = (q_pos >= 0 && q_pos < q_count) ? q_pos : -1;
    int i, j, n = 0, m = 0, new_pos = -1, tries;

    if (q_count < 2)
        return;
    items = av_malloc_array(q_count, sizeof(*items));
    flags = av_malloc(q_count);
    seqs = av_malloc_array(q_count, sizeof(*seqs));
    pairs = av_malloc_array(q_count, sizeof(*pairs));
    if (!items || !flags || !seqs || !pairs)
        goto end;

    for (i = 0; i < pos; i++) {                 /* before the playing item: unchanged */
        items[n] = q_items[i];
        flags[n] = q_played[i];
        seqs[n++] = q_seq[i];
    }
    for (i = pos + 1; i < q_count; i++) {       /* after it, but already played */
        if (!q_played[i])
            continue;
        items[n] = q_items[i];
        flags[n] = 1;
        seqs[n++] = q_seq[i];
    }
    if (pos >= 0) {                             /* the playing item */
        new_pos = n;
        items[n] = q_items[pos];
        flags[n] = q_played[pos];
        seqs[n++] = q_seq[pos];
    }
    for (i = pos + 1; i < q_count; i++) {       /* the rest: still to play */
        if (q_played[i])
            continue;
        pairs[m].item = q_items[i];
        pairs[m].seq = q_seq[i];
        m++;
    }

    if (shuffle && m >= 3) {
        queue_seed();
        orig = av_malloc_array(m, sizeof(*orig));
        if (orig)
            memcpy(orig, pairs, m * sizeof(*pairs));
        for (tries = 0; tries < 8; tries++) {   /* shuffle until the order really is different */
            for (i = m - 1; i > 0; i--) {
                j = rand() % (i + 1);
                t = pairs[i];
                pairs[i] = pairs[j];
                pairs[j] = t;
            }
            if (!orig || memcmp(orig, pairs, m * sizeof(*pairs)))
                break;
        }
    } else if (shuffle && m == 2) {
        t = pairs[0];                           /* two items: swap them */
        pairs[0] = pairs[1];
        pairs[1] = t;
    } else if (!shuffle && m > 1) {
        qsort(pairs, m, sizeof(*pairs), queue_pair_cmp);
    }
    for (i = 0; i < m; i++) {
        items[n] = pairs[i].item;
        flags[n] = 0;
        seqs[n++] = pairs[i].seq;
    }

    memcpy(q_items, items, n * sizeof(*items));
    memcpy(q_played, flags, n);
    memcpy(q_seq, seqs, n * sizeof(*seqs));
    if (new_pos >= 0)
        q_pos = new_pos;
    q_forced = -1;
end:
    av_free(items);
    av_free(flags);
    av_free(seqs);
    av_free(pairs);
    av_free(orig);
}

/* Turn shuffle on (the queue is shuffled) or off (the original order comes back) */
static void queue_set_shuffle(int on)
{
    q_shuffle = on;
    queue_reorder(on);
}

/* Take an item out of the queue. If it was playing, the next one takes its place. */
static void queue_remove(int idx)
{
    char *gone;
    int i;

    if (idx < 0 || idx >= q_count)
        return;
    gone = q_items[idx];
    if (gone == q_sleep_item)
        q_sleep_item = NULL;
    if (gone == xf_name)
        xf_name = NULL;
    for (i = idx; i < q_count - 1; i++) {
        q_items[i] = q_items[i + 1];
        q_played[i] = q_played[i + 1];
        q_seq[i] = q_seq[i + 1];
    }
    q_count--;
    if (idx == q_pos) {
        q_pos--;                                /* the item that followed it is now at idx */
        q_step = 1;
        queue_bury(gone);                       /* the stream that is playing it may still read the name */
    } else {
        if (idx < q_pos)
            q_pos--;
        av_free(gone);
    }
    if (q_forced == idx)
        q_forced = -1;
    else if (q_forced > idx)
        q_forced--;
}

/* Move an item to a new place in the queue. The item that is playing keeps playing. */
static void queue_move(int from, int to)
{
    char *item;
    unsigned char played;
    int seq, i;

    if (from == to || from < 0 || to < 0 || from >= q_count || to >= q_count)
        return;
    item = q_items[from];
    played = q_played[from];
    seq = q_seq[from];
    if (from < to) {
        for (i = from; i < to; i++) {
            q_items[i] = q_items[i + 1];
            q_played[i] = q_played[i + 1];
            q_seq[i] = q_seq[i + 1];
        }
    } else {
        for (i = from; i > to; i--) {
            q_items[i] = q_items[i - 1];
            q_played[i] = q_played[i - 1];
            q_seq[i] = q_seq[i - 1];
        }
    }
    q_items[to] = item;
    q_played[to] = played;
    q_seq[to] = seq;
    if (q_pos == from)
        q_pos = to;
    else if (from < q_pos && q_pos <= to)
        q_pos--;
    else if (to <= q_pos && q_pos < from)
        q_pos++;
    if (!q_shuffle) {                           /* with shuffle off, a hand-made order becomes the original order */
        for (i = 0; i < q_count; i++)
            q_seq[i] = i;
        q_seq_next = q_count;
    }
}

/* Compare names so that "track2" comes before "track10" */
static int natural_cmp(const char *a, const char *b)
{
    while (*a && *b) {
        if (isdigit((unsigned char)*a) && isdigit((unsigned char)*b)) {
            char *ea, *eb;
            unsigned long long na = strtoull(a, &ea, 10);
            unsigned long long nb = strtoull(b, &eb, 10);

            if (na != nb)
                return na < nb ? -1 : 1;
            a = ea;
            b = eb;
        } else {
            int ca = tolower((unsigned char)*a);
            int cb = tolower((unsigned char)*b);

            if (ca != cb)
                return ca < cb ? -1 : 1;
            a++;
            b++;
        }
    }
    return (*a != 0) - (*b != 0);
}

static int name_cmp(const void *a, const void *b)
{
    return natural_cmp(*(char *const *)a, *(char *const *)b);
}

/* Is this a file we should pick up when a folder is added? */
static int is_media_file(const char *name)
{
    static const char *exts[] = { ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv",
                                  ".flv", ".ts", ".mp3", ".flac", ".wav", ".m4a", ".opus",
                                  ".ogg", ".aac", ".wma", NULL };
    const char *dot = strrchr(name, '.');
    int i;

    if (!dot)
        return 0;
    for (i = 0; exts[i]; i++)
        if (!av_strcasecmp(dot, exts[i]))
            return 1;
    return 0;
}

/* Add a file or URL to the queue, or every media file inside a folder (sorted by name) */
static void queue_add_path(const char *path)
{
    struct stat st;
    DIR *d;
    struct dirent *e;
    char **names = NULL;
    char full[PATH_MAX];
    int count = 0, i;

    if (stat(path, &st) != 0 || !S_ISDIR(st.st_mode)) {
        queue_add(path);
        return;
    }
    d = opendir(path);
    if (!d)
        return;
    while ((e = readdir(d))) {
        char **bigger;

        if (e->d_name[0] == '.' || !is_media_file(e->d_name))
            continue;
        bigger = av_realloc_array(names, count + 1, sizeof(*names));
        if (!bigger)
            break;
        names = bigger;
        names[count] = av_strdup(e->d_name);
        if (names[count])
            count++;
    }
    closedir(d);
    qsort(names, count, sizeof(*names), name_cmp);
    for (i = 0; i < count; i++) {
        snprintf(full, sizeof(full), "%s/%s", path, names[i]);
        queue_add(full);
        av_free(names[i]);
    }
    av_free(names);
}

/* ----- one player at a time: later launches hand their files to the running one ----- */
static char ui_inbox_path[1024];
static int ui_lock_fd = -1;
static int64_t ui_inbox_next = 0;       /* when to look in the inbox again */

static void ui_runtime_path(char *out, size_t size, const char *name)
{
    const char *dir = getenv("XDG_RUNTIME_DIR");

    snprintf(out, size, "%s/%s", (dir && *dir) ? dir : "/tmp", name);
}

/* Returns 1 if we are the only player, 0 if another one is already running */
static int ui_take_lock(void)
{
    char lock[1024];

    ui_runtime_path(lock, sizeof(lock), "ffplay-custom.lock");
    ui_runtime_path(ui_inbox_path, sizeof(ui_inbox_path), "ffplay-custom.inbox");
    ui_lock_fd = open(lock, O_CREAT | O_RDWR, 0600);
    if (ui_lock_fd < 0)
        return 1;                   /* cannot lock: just carry on as the only player */
    fcntl(ui_lock_fd, F_SETFD, FD_CLOEXEC);     /* the file dialogs must not keep the lock */
    if (flock(ui_lock_fd, LOCK_EX | LOCK_NB) != 0)
        return 0;
    unlink(ui_inbox_path);          /* forget anything left over from an earlier run */
    return 1;
}

/* Leave a command for the running player: 'o' = open now, 'a' = add to the queue */
static void ui_inbox_send(char cmd, const char *path)
{
    FILE *f = fopen(ui_inbox_path, "a");

    if (!f)
        return;
    fprintf(f, "%c%s\n", cmd, path);
    fclose(f);
}

/* Read what the other launches and the file dialogs left in the inbox.
   is = the stream playing now, or NULL on the idle screen. */
static void ui_inbox_tick(VideoState *is)
{
    char work[1100], line[PATH_MAX + 2];
    FILE *f;
    int opened = 0;

    if (av_gettime_relative() < ui_inbox_next)
        return;
    ui_inbox_next = av_gettime_relative() + 300000;

    snprintf(work, sizeof(work), "%s.work", ui_inbox_path);
    if (rename(ui_inbox_path, work) != 0)
        return;                     /* nothing in the inbox */
    f = fopen(work, "r");
    if (!f)
        return;
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\n")] = 0;
        if (!line[0] || !line[1])
            continue;
        if (line[0] == 'o' && !opened && !is) {
            queue_clear();          /* nothing is playing: open now, with a fresh queue */
            opened = 1;
        }                           /* while something plays, an 'o' is added to the queue like an 'a' */
        if (line[0] == 'o' || line[0] == 'a')
            queue_add_path(line + 1);
    }
    fclose(f);
    unlink(work);

    /* Open now: stop what is playing, so the new queue starts from its first item */
    if (opened && is) {
        SDL_Event ev;

        ev.type = FF_QUIT_EVENT;
        ev.user.data1 = is;
        SDL_PushEvent(&ev);
    }
}

/* Close the current stream so the main loop can go on to the next queue item */
static void ui_end_stream(VideoState *is)
{
    ui_session_volume = is->audio_volume;   /* the next item starts at this volume */
    volume_save(is->audio_volume);
    stream_close(is);
    SDL_FlushEvent(FF_QUIT_EVENT);          /* drop a leftover end-of-file event */
    queue_reap();                           /* no stream is running: removed names can go */
    ui_seek_want = 0;
    ui_hover = 0;
    ui_drag = 0;
}

/* ----- file dialogs (zenity), run in a thread so the player keeps working ----- */
static SDL_atomic_t ui_pick_busy;       /* 1 while a file dialog is open */

static int ui_pick_thread(void *arg)
{
    int item = (int)(intptr_t)arg;
    const char *cmd;
    char what;
    char line[PATH_MAX + 2];
    FILE *p;
    int status;

    if (item == 0) {            /* Open File... */
        cmd = "zenity --file-selection --title='Open File' 2>/dev/null";
        what = 'o';
    } else if (item == 1) {     /* Open Folder... */
        cmd = "zenity --file-selection --directory --title='Open Folder' 2>/dev/null";
        what = 'o';
    } else {                    /* Add to Queue... (one or more files) */
        cmd = "zenity --file-selection --multiple --separator='\n' --title='Add to Queue' 2>/dev/null";
        what = 'a';
    }

    p = popen(cmd, "r");
    if (p) {
        while (fgets(line, sizeof(line), p)) {
            line[strcspn(line, "\n")] = 0;
            if (line[0])
                ui_inbox_send(what, line);
        }
        status = pclose(p);
        if (status != -1 && ((status >> 8) & 0xff) == 127)
            fprintf(stderr, "ffplay-custom: zenity is needed for the file dialogs (sudo apt install zenity)\n");
    }
    SDL_AtomicSet(&ui_pick_busy, 0);
    return 0;
}

static void ui_pick_start(int item)
{
    SDL_Thread *t;

    if (!SDL_AtomicCAS(&ui_pick_busy, 0, 1))
        return;                 /* a dialog is already open */
    t = SDL_CreateThread(ui_pick_thread, "file dialog", (void *)(intptr_t)item);
    if (t)
        SDL_DetachThread(t);
    else
        SDL_AtomicSet(&ui_pick_busy, 0);
}

/* ----- the menu: right-click panel while playing, next to the logo on the idle screen ----- */
#define UI_MENU_SCALE 2         /* text size: 2 = twice the 8x16 font */
static int ui_menu_rowh = 44;           /* height of one menu row: smaller when the window is short */
#define UI_MENU_ROW ui_menu_rowh

#define UI_MENU_ITEMS 5         /* rows in the menu */
#define UI_ROW_OPEN  0          /* Open: File... and Folder... appear beside it */
#define UI_ROW_QUEUE 1
#define UI_ROW_INFO  2
#define UI_ROW_PREFS 3
#define UI_ROW_QUIT  4

static const char *ui_menu_label[UI_MENU_ITEMS] = { "Open", "Queue", "Media Info",
                                                    "Preferences...", "Quit" };
static int ui_idle = 0;         /* 1 while the idle screen is showing */
static int ui_menu_open = 0;    /* 1 while the right-click menu is showing */
static int ui_menu_x, ui_menu_y;    /* where the right-click menu was opened */
static int ui_menu_hover = -1;  /* menu row under the mouse (-1 = none) */
static int ui_q_open = 0;       /* 1 while the queue panel is showing beside the menu */
static int ui_q_scroll = 0;     /* first queue item shown in the panel */
static double ui_q_off = 0.0;   /* rows the list is still sliding after a scroll, so it glides instead of jumping */
static int ui_q_last_scroll = -1;
static int64_t ui_q_off_t = 0;
static int ui_q_drag = -1;      /* queue item being dragged (-1 = none) */
static int ui_q_drag_y = 0;     /* mouse height while dragging */
static int ui_info_open = 0;    /* 1 while the Media Info panel is showing beside the menu */
static int ui_open_open = 0;    /* 1 while the File / Folder choices are showing beside "Open" */
static int ui_open_hover = -1;  /* the choice under the mouse (0 = File, 1 = Folder) */
static int ui_q_reveal = 0;     /* 1 = the queue panel was just opened: scroll to the playing item */
static int ui_ctx_open = 0;     /* 1 while the right-click menu of a queue item is showing */
static int ui_ctx_x, ui_ctx_y;  /* where it was opened */
static int ui_ctx_hover = -1;   /* its row under the mouse */
static char *ui_ctx_name = NULL;    /* the queue item it is for */
static double ui_chip_e = 0.0;          /* 0 to 1: how far the sleep timer row has changed into its choices */
static int64_t ui_chip_last = 0;
static double ui_xf_e = 0.0;            /* 0 to 1: how far the crossfade row has changed into its choices */
static int64_t ui_xf_last = 0;
static int ui_xf_anim = 0;
static int ui_chip_anim = 0;            /* 1 = it is still gliding */
static int ui_q_hover_kind = 0;     /* what the mouse is over in the queue panel (UI_Q_NONE ...) */
static int ui_q_hover_idx = -1;     /* ... and which item or choice */
static int64_t ui_menu_anim_t0 = 0; /* when the popup menu opened (its rows fade in from then) */
static int64_t ui_q_anim_t0 = 0;    /* when the queue panel opened (its rows fade in from then) */
static int64_t ui_menu_last_move = 0;      /* when the mouse last moved over the popup menu */
static int64_t ui_q_scroll_next = 0;       /* earliest time for the next scroll step while dragging */
static int ui_q_autoscroll(void);
static VideoState *ui_menu_stream = NULL;   /* the stream the menu is drawn over (NULL = idle screen) */

/* Draw text bigger: every pixel of the 8x16 font becomes a scale x scale square */
static void ui_text_big(int x, int y, const char *s, int scale)
{
    for (; *s; s++, x += 8 * scale) {
        const uint8_t *glyph = avpriv_vga16_font + (uint8_t)*s * 16;
        int row, col;

        for (row = 0; row < 16; row++)
            for (col = 0; col < 8; col++)
                if (glyph[row] & (0x80 >> col)) {
                    SDL_Rect px = { x + col * scale, y + row * scale, scale, scale };

                    SDL_RenderFillRect(renderer, &px);
                }
    }
}

/* The logo: a round badge in the bar color with a white play triangle */
static void ui_logo(int cx, int cy, int size)
{
    SDL_Rect disc = { cx - size / 2, cy - size / 2, size, size };
    int tri_h = size / 2;
    int tri_w = size * 2 / 5;
    int x0 = cx - tri_w / 3;        /* a little to the left, so it looks centered */
    int row;

    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 255);
    ui_pill(&disc);                 /* a square pill is a circle */
    SDL_SetRenderDrawColor(renderer, 240, 240, 240, 255);
    for (row = 0; row < tri_h; row++) {
        /* widest in the middle row, a point at the top and bottom */
        double t = 1.0 - fabs(2.0 * row / (tri_h - 1) - 1.0);
        SDL_Rect line = { x0, cy - tri_h / 2 + row, (int)(tri_w * t), 1 };

        if (line.w > 0)
            SDL_RenderFillRect(renderer, &line);
    }
}

/* ---- sharp text (SDL2_ttf), frosted glass and the Preferences panel ---- */
#include <SDL_ttf.h>

/* ----- sharp text ----- */
#define UI_FONTS_MAX 8
#define UI_TEXT_CACHE 128
static int ui_ttf_state = 0;            /* 0 = not tried yet, 1 = working, -1 = not available */
static char ui_font_path[512];
static struct { int px; TTF_Font *font; } ui_fonts[UI_FONTS_MAX];
static struct { char s[96]; int px; SDL_Texture *tex; int w, h; } ui_tc[UI_TEXT_CACHE];
static int ui_tc_next = 0;

/* Find a font file and start SDL_ttf. If anything fails we keep using the pixel font. */
static void ui_ttf_init(void)
{
    static const char *fallbacks[] = { "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                                       "/usr/share/fonts/TTF/DejaVuSans.ttf", NULL };
    char path[512] = "";
    FILE *p;
    int i;

    ui_ttf_state = -1;
    if (TTF_Init() != 0)
        return;
    if (cfg_font[0])
        snprintf(path, sizeof(path), "%s", cfg_font);
    if (!path[0] || access(path, R_OK) != 0) {
        /* ask fontconfig for the system's default sans-serif font */
        path[0] = 0;
        p = popen("fc-match -f '%{file}' sans-serif 2>/dev/null", "r");
        if (p) {
            if (!fgets(path, sizeof(path), p))
                path[0] = 0;
            pclose(p);
        }
    }
    for (i = 0; fallbacks[i] && (!path[0] || access(path, R_OK) != 0); i++)
        snprintf(path, sizeof(path), "%s", fallbacks[i]);
    if (access(path, R_OK) != 0)
        return;
    snprintf(ui_font_path, sizeof(ui_font_path), "%s", path);
    ui_ttf_state = 1;
}

/* The font at a given pixel height (opened once, then kept) */
static TTF_Font *ui_font(int px)
{
    int i;

    if (ui_ttf_state == 0)
        ui_ttf_init();
    if (ui_ttf_state < 0)
        return NULL;
    for (i = 0; i < UI_FONTS_MAX && ui_fonts[i].font; i++)
        if (ui_fonts[i].px == px)
            return ui_fonts[i].font;
    if (i == UI_FONTS_MAX)
        return NULL;
    ui_fonts[i].font = TTF_OpenFont(ui_font_path, px);
    if (!ui_fonts[i].font) {
        ui_ttf_state = -1;
        return NULL;
    }
    TTF_SetFontHinting(ui_fonts[i].font, TTF_HINTING_LIGHT);
    ui_fonts[i].px = px;
    return ui_fonts[i].font;
}

/* A texture with the text drawn in white (kept in a small cache). NULL if there is no font. */
static SDL_Texture *ui_text_tex(const char *s, int px, int *w, int *h)
{
    TTF_Font *font = ui_font(px);
    SDL_Color white = { 255, 255, 255, 255 };
    SDL_Surface *surf;
    int i;

    if (!font || !*s)
        return NULL;
    for (i = 0; i < UI_TEXT_CACHE; i++)
        if (ui_tc[i].tex && ui_tc[i].px == px && !strcmp(ui_tc[i].s, s)) {
            *w = ui_tc[i].w;
            *h = ui_tc[i].h;
            return ui_tc[i].tex;
        }
    surf = TTF_RenderUTF8_Blended(font, s, white);
    if (!surf)
        return NULL;
    i = ui_tc_next;
    ui_tc_next = (ui_tc_next + 1) % UI_TEXT_CACHE;
    if (ui_tc[i].tex)
        SDL_DestroyTexture(ui_tc[i].tex);
    ui_tc[i].tex = SDL_CreateTextureFromSurface(renderer, surf);
    snprintf(ui_tc[i].s, sizeof(ui_tc[i].s), "%s", s);
    ui_tc[i].px = px;
    ui_tc[i].w = *w = surf->w;
    ui_tc[i].h = *h = surf->h;
    SDL_FreeSurface(surf);
    return ui_tc[i].tex;
}

/* Width of a text in pixels */
static int ui_text_width(const char *s, int px)
{
    int w = 0, h = 0;
    TTF_Font *font = ui_font(px);

    if (font && TTF_SizeUTF8(font, s, &w, &h) == 0)
        return w;
    return (int)strlen(s) * 8 * (px < 20 ? 1 : 2);      /* pixel font */
}

/* Draw text with its left edge at x and its middle at cy. px = text height in pixels. */
static void ui_label(int x, int cy, const char *s, int px, int r, int g, int b, int a)
{
    int w = 0, h = 0;
    SDL_Texture *tex = ui_text_tex(s, px, &w, &h);
    SDL_Rect dst;

    a = (int)(a * ui_fade);

    if (!tex) {
        /* no font available: use the pixel font */
        SDL_SetRenderDrawColor(renderer, r, g, b, a);
        if (px < 20)
            ui_text(x, cy - 8, s);
        else
            ui_text_big(x, cy - 16, s, 2);
        return;
    }
    dst.x = x;
    dst.y = cy - h / 2;
    dst.w = w;
    dst.h = h;
    ui_ink(&r, &g, &b);                         /* dark text on the light glass */
    SDL_SetTextureColorMod(tex, r, g, b);
    SDL_SetTextureAlphaMod(tex, a);
    SDL_RenderCopy(renderer, tex, NULL, &dst);
}

/* Draw text with its middle at cx */
static void ui_label_c(int cx, int cy, const char *s, int px, int r, int g, int b, int a)
{
    ui_label(cx - ui_text_width(s, px) / 2, cy, s, px, r, g, b, a);
}

/* A soft arrowhead for the menus: a flat, fine chevron with a faint halo, pointing left (dir = -1) or
   right (dir = 1). cx, cy = its middle. a = how strong it is (0 to 255). */
static void ui_arrow(int cx, int cy, int dir, int a)
{
    int k, tail = cx - dir * 3, tip = cx + dir * 3, h = 5;

    a = av_clip((int)(a * ui_fade), 0, 255);       /* (a can arrive below 0 while the menu fades in) */
    for (k = -1; k <= 1; k++) {
        SDL_SetRenderDrawColor(renderer, 225, 225, 225, k ? a / 5 : a);
        SDL_RenderDrawLine(renderer, tail, cy - h + k, tip, cy + k);
        SDL_RenderDrawLine(renderer, tip, cy + k, tail, cy + h + k);
    }
}

/* ----- rounded rectangles ----- */

/* How far in from the left and right edge a row of a rounded rectangle starts.
   The corner is a squircle, not a circle: it flows into the straight edge more gently. */
static int ui_rr_inset(int row, int h, int r)
{
    double dy;

    if (row < r)
        dy = r - row - 0.5;
    else if (row >= h - r)
        dy = row - (h - r) + 0.5;
    else
        return 0;
    return (int)(r - r * cbrt(1.0 - pow(dy / r, 3.0)) + 0.5);
}

/* Fill a rounded rectangle with the current draw color */
static void ui_rr_fill(const SDL_Rect *t, int r)
{
    SDL_Rect line;
    int row, inset;

    r = FFMIN(r, FFMIN(t->w, t->h) / 2);
    for (row = 0; row < t->h; row++) {
        inset = ui_rr_inset(row, t->h, r);
        line.x = t->x + inset;
        line.y = t->y + row;
        line.w = t->w - 2 * inset;
        line.h = 1;
        if (line.w > 0)
            SDL_RenderFillRect(renderer, &line);
    }
}

/* A soft shadow under a panel: a few rounded shapes, each a little bigger and fainter */
static void ui_shadow(const SDL_Rect *t, int r)
{
    SDL_Rect e;
    int i;

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = ui_shadows_on ? 6 : 0; i >= 1; i--) {         /* the black shadow (skipped when the switch is off) */
        e.x = t->x - i * 3;
        e.y = t->y - i * 3 + 10;
        e.w = t->w + i * 6;
        e.h = t->h + i * 6;
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 7);
        ui_rr_fill(&e, r + i * 3);
    }
    for (i = 4; i >= 1; i--) {      /* a faint haze of light at the edge, in place of a line: the panel floats */
        e.x = t->x - i * 2;
        e.y = t->y - i * 2;
        e.w = t->w + i * 4;
        e.h = t->h + i * 4;
        SDL_SetRenderDrawColor(renderer, 255, 255, 255, 3);
        ui_rr_fill(&e, r + i * 2);
    }
}

/* ----- frosted glass ----- */
static SDL_Texture *ui_scene_tex = NULL;    /* the finished picture, so it can be blurred */
static SDL_Texture *ui_blur_tex[4];         /* the picture at 1/2, 1/4, 1/8 and 1/16 size */
static SDL_Texture *ui_blob_tex = NULL;     /* a tiny picture of glowing blobs (idle screen) */
static int ui_gw = 0, ui_gh = 0;            /* window size the textures were made for */

/* ----- the cover art backdrop -----
   While an audio file with embedded cover art plays, a field of the cover's own colors fills the window
   behind the picture. It is a soft mesh of 17 x 10 colored points: the colors come from the cover (averaged
   down to that size once per file), the points drift slowly, and the whole thing brightens and swells a
   little with the loudness of the music. */
#define UI_BD_W 17
#define UI_BD_H 10
static SDL_Texture *ui_bd_tex = NULL;           /* the cover, tiny, to read its colors from */
static SDL_Color ui_bd_col[UI_BD_H][UI_BD_W];
static char ui_bd_key[1024] = "";               /* the file the colors were taken from */
static float ui_bd_level = 0.0f;                /* the loudness, smoothed */

static SDL_Texture *ui_make_target(int w, int h);

/* Does this stream show cover art (a picture attached to an audio file)? */
static int ui_has_cover(VideoState *is)
{
    return is && is->video_st && (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) && is->vid_texture;
}

/* Average the cover down to one color per mesh point */
static void ui_cover_colors(VideoState *is, int flip)
{
    enum { TW = 192, TH = 108 };
    static uint32_t px[TW * TH];
    SDL_Texture *prev = SDL_GetRenderTarget(renderer);
    int i, j, x, y, ok = 0;

    memset(ui_bd_col, 0, sizeof(ui_bd_col));
    if (!ui_bd_tex)
        ui_bd_tex = ui_make_target(TW, TH);
    if (!ui_bd_tex)
        return;
    SDL_SetRenderTarget(renderer, ui_bd_tex);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, NULL, 0, NULL, flip ? SDL_FLIP_VERTICAL : 0);
    ok = SDL_RenderReadPixels(renderer, NULL, SDL_PIXELFORMAT_ARGB8888, px, TW * 4) == 0;
    SDL_SetRenderTarget(renderer, prev);
    if (!ok)
        return;
    for (j = 0; j < UI_BD_H; j++) {
        for (i = 0; i < UI_BD_W; i++) {
            int x0 = i * TW / UI_BD_W, x1 = FFMAX((i + 1) * TW / UI_BD_W, x0 + 1);
            int y0 = j * TH / UI_BD_H, y1 = FFMAX((j + 1) * TH / UI_BD_H, y0 + 1);
            double r = 0, g = 0, b = 0, n = 0, lum;

            for (y = y0; y < y1; y++)
                for (x = x0; x < x1; x++) {
                    uint32_t p = px[y * TW + x];

                    r += (p >> 16) & 255;
                    g += (p >> 8) & 255;
                    b += p & 255;
                    n++;
                }
            r /= n;
            g /= n;
            b /= n;
            lum = 0.30 * r + 0.59 * g + 0.11 * b;       /* a little more color than the cover has */
            ui_bd_col[j][i].r = (Uint8)av_clipd(lum + (r - lum) * 1.3, 0, 255);
            ui_bd_col[j][i].g = (Uint8)av_clipd(lum + (g - lum) * 1.3, 0, 255);
            ui_bd_col[j][i].b = (Uint8)av_clipd(lum + (b - lum) * 1.3, 0, 255);
            ui_bd_col[j][i].a = 255;
        }
    }
}

static void ui_cover_backdrop(VideoState *is, int flip)
{
    static int idx[(UI_BD_W - 1) * (UI_BD_H - 1) * 6];
    static int idx_ready = 0;
    SDL_Vertex v[UI_BD_H * UI_BD_W];
    SDL_Rect veil;
    double t = av_gettime_relative() / 1000000.0, u, w, shimmer, bright, swell;
    int i, j, k = 0, W = is->width, H = is->height;
    float target;
    double bdk = ui_flow_video(is) ? ui_vflow_ep : 1.0;     /* the backdrop fades in while the video shrinks into its tile */

    if (!(ui_has_cover(is) || ui_flow_video(is)) || W <= 0 || H <= 0)
        return;
    if (strncmp(ui_bd_key, is->filename, sizeof(ui_bd_key) - 1)) {     /* a new file: take its colors */
        snprintf(ui_bd_key, sizeof(ui_bd_key), "%s", is->filename);
        ui_cover_colors(is, flip);
    }
    if (!idx_ready) {
        for (j = 0; j < UI_BD_H - 1; j++)
            for (i = 0; i < UI_BD_W - 1; i++) {
                int a = j * UI_BD_W + i;

                idx[k++] = a;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W + 1;
                idx[k++] = a + UI_BD_W;
            }
        idx_ready = 1;
    }

    target = is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f);
    ui_bd_level += (target - ui_bd_level) * 0.15f;
    bright = 0.62 + 0.38 * ui_bd_level;
    swell = 1.0 + 0.03 * ui_bd_level;
    for (j = 0; j < UI_BD_H; j++) {
        for (i = 0; i < UI_BD_W; i++) {
            SDL_Vertex *p = &v[j * UI_BD_W + i];

            u = i / (double)(UI_BD_W - 1);
            w = j / (double)(UI_BD_H - 1);
            /* the points reach past the window, so their drifting never shows an edge */
            p->position.x = (float)(((u - 0.5) * 1.18 * swell + 0.5 + 0.035 * sin(t * 0.31 + j * 0.9 + i * 0.45)) * W);
            p->position.y = (float)(((w - 0.5) * 1.18 * swell + 0.5 + 0.045 * cos(t * 0.27 + i * 0.7 + j * 0.55)) * H);
            shimmer = bright * (1.0 + 0.10 * sin(t * 0.8 + i * 1.3 + j * 1.7));
            p->color.r = (Uint8)av_clipd(ui_bd_col[j][i].r * shimmer, 0, 255);
            p->color.g = (Uint8)av_clipd(ui_bd_col[j][i].g * shimmer, 0, 255);
            p->color.b = (Uint8)av_clipd(ui_bd_col[j][i].b * shimmer, 0, 255);
            p->color.a = (Uint8)(255 * bdk);
            p->tex_coord.x = 0;
            p->tex_coord.y = 0;
        }
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_RenderGeometry(renderer, NULL, v, UI_BD_H * UI_BD_W, idx, (UI_BD_W - 1) * (UI_BD_H - 1) * 6);

    /* a dark veil, so the controls on top stay readable */
    veil.x = 0;
    veil.y = 0;
    veil.w = W;
    veil.h = H;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, (int)(45 * bdk));
    SDL_RenderFillRect(renderer, &veil);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Keep the backdrop moving: the cover is a still picture, so nothing else would redraw the window */
static void ui_cover_tick(VideoState *is)
{
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if ((ui_has_cover(is) || ui_flow_video(is)) && !is->paused && now - last > 33000) {
        last = now;
        is->force_refresh = 1;
    }
}

/* ----- the aurora: the backdrop for audio without cover art -----
   The same soft mesh as the cover art backdrop, but its colors are made up as it goes, from your bar color:
   slow curtains of light drift across it and shift in hue. The loudness of the last second or so is kept in
   a row of values, one per column, and it travels across the window, so the music seems to ripple through. */
static void ui_rgb2hsv(int r, int g, int b, double *h, double *s, double *v)
{
    double rf = r / 255.0, gf = g / 255.0, bf = b / 255.0;
    double mx = FFMAX3(rf, gf, bf), mn = FFMIN3(rf, gf, bf), d = mx - mn;

    *v = mx;
    *s = mx > 0 ? d / mx : 0;
    if (d <= 0)
        *h = 0;
    else if (mx == rf)
        *h = fmod((gf - bf) / d, 6.0) / 6.0;
    else if (mx == gf)
        *h = ((bf - rf) / d + 2.0) / 6.0;
    else
        *h = ((rf - gf) / d + 4.0) / 6.0;
    if (*h < 0)
        *h += 1.0;
}

static void ui_hsv2rgb(double h, double s, double v, SDL_Color *c)
{
    double r, g, b, f, p, q, t;
    int i;

    h = (h - floor(h)) * 6.0;
    i = (int)h;
    f = h - i;
    p = v * (1 - s);
    q = v * (1 - s * f);
    t = v * (1 - s * (1 - f));
    switch (i % 6) {
    case 0:  r = v; g = t; b = p; break;
    case 1:  r = q; g = v; b = p; break;
    case 2:  r = p; g = v; b = t; break;
    case 3:  r = p; g = q; b = v; break;
    case 4:  r = t; g = p; b = v; break;
    default: r = v; g = p; b = q; break;
    }
    c->r = (Uint8)av_clipd(r * 255, 0, 255);
    c->g = (Uint8)av_clipd(g * 255, 0, 255);
    c->b = (Uint8)av_clipd(b * 255, 0, 255);
    c->a = 255;
}

/* Draw the aurora behind an audio-only stream. Returns 1 if it was drawn. */
static int ui_aurora_backdrop(VideoState *is)
{
    static float hist[UI_BD_W];                 /* the loudness of the last moments, one value per column */
    static int64_t hist_at = 0;
    static float lvl = 0.0f;
    static int idx[(UI_BD_W - 1) * (UI_BD_H - 1) * 6];
    static int idx_ready = 0;
    SDL_Vertex v[UI_BD_H * UI_BD_W];
    double t = av_gettime_relative() / 1000000.0, h0, s0, v0, u, w, band, curtain, vw, val, dx, dy;
    int64_t now = av_gettime_relative();
    int i, j, k = 0, W = is->width, H = is->height;

    if (!is->audio_st || ui_has_cover(is) || W <= 0 || H <= 0)
        return 0;
    if (!idx_ready) {
        for (j = 0; j < UI_BD_H - 1; j++)
            for (i = 0; i < UI_BD_W - 1; i++) {
                int a = j * UI_BD_W + i;

                idx[k++] = a;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W;
                idx[k++] = a + 1;
                idx[k++] = a + UI_BD_W + 1;
                idx[k++] = a + UI_BD_W;
            }
        idx_ready = 1;
    }
    lvl += ((is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f)) - lvl) * 0.2f;
    if (now - hist_at > 60000 || now < hist_at) {       /* the ripple moves one column to the left */
        memmove(hist, hist + 1, sizeof(float) * (UI_BD_W - 1));
        hist[UI_BD_W - 1] = lvl;
        hist_at = now;
    }
    ui_rgb2hsv(cfg_bar_r, cfg_bar_g, cfg_bar_b, &h0, &s0, &v0);
    s0 = FFMAX(s0, 0.55);

    for (j = 0; j < UI_BD_H; j++) {
        for (i = 0; i < UI_BD_W; i++) {
            SDL_Vertex *p = &v[j * UI_BD_W + i];

            u = i / (double)(UI_BD_W - 1);
            w = j / (double)(UI_BD_H - 1);
            band = 0.5 + 0.5 * sin(i * 0.55 + t * 0.30 + 1.4 * sin(j * 0.6 + t * 0.20));
            curtain = pow(band, 2.2);                           /* the bright curtains */
            vw = 0.2 + 0.8 * pow(1.0 - w, 0.8);                 /* they hang from the top */
            val = 0.08 + 0.50 * curtain * vw + 0.50 * hist[i] * (0.4 + 0.6 * vw);
            val *= 0.75 + 0.50 * lvl;
            dx = u - 0.5;
            dy = w - 0.5;
            val *= 1.0 - 0.8 * (dx * dx + dy * dy);             /* darker toward the corners */
            ui_hsv2rgb(h0 + 0.06 * sin(t * 0.21 + i * 0.5 + j * 0.8) + 0.10 * curtain,
                       av_clipd(s0 * (1.05 - 0.30 * curtain), 0.0, 1.0), av_clipd(val, 0.0, 0.9), &p->color);
            p->position.x = (float)(((u - 0.5) * 1.12 + 0.5 + 0.02 * sin(t * 0.25 + j * 0.9 + i * 0.4)) * W);
            p->position.y = (float)(((w - 0.5) * 1.12 + 0.5 + 0.03 * cos(t * 0.22 + i * 0.6 + j * 0.5)) * H);
            p->tex_coord.x = 0;
            p->tex_coord.y = 0;
        }
    }
    SDL_RenderGeometry(renderer, NULL, v, UI_BD_H * UI_BD_W, idx, (UI_BD_W - 1) * (UI_BD_H - 1) * 6);
    return 1;
}

/* ----- the bubble party: the backdrop for audio without cover art -----
   Soft glowing bubbles in your bar color float up the window. The loudness of the music makes them rise faster and
   glow bigger; a sudden loud hit (a beat) makes them all pop out for a moment. */
static int ui_bubble_backdrop(VideoState *is)
{
    enum { NB = 26, NSEG = 20 };
    static SDL_Vertex v[NB * (NSEG + 1)];
    static int idx[NB * NSEG * 3];
    static int idx_ready = 0;
    static double drift = 0.0, last_t = 0.0;
    static float lvl = 0.0f, slow = 0.0f, pulse = 0.0f;
    double t = av_gettime_relative() / 1000000.0, dt, h0, s0, v0;
    int W = is->width, H = is->height, i, k, j;
    double m;
    SDL_Color c;
    SDL_Rect bg;

    if (!is->audio_st || ui_has_cover(is) || W <= 0 || H <= 0)
        return 0;
    if (!idx_ready) {
        for (i = 0, k = 0; i < NB; i++)
            for (j = 0; j < NSEG; j++) {
                idx[k++] = i * (NSEG + 1);
                idx[k++] = i * (NSEG + 1) + 1 + j;
                idx[k++] = i * (NSEG + 1) + 1 + (j + 1) % NSEG;
            }
        idx_ready = 1;
    }
    dt = last_t > 0.0 ? av_clipd(t - last_t, 0.0, 0.1) : 0.0;
    last_t = t;
    if (is->paused)
        dt = 0.0;
    lvl += ((is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f)) - lvl) * 0.2f;
    slow += (lvl - slow) * 0.04f;
    pulse = FFMAX(0.0f, pulse - (float)dt * 2.2f);
    if (lvl - slow > 0.10f && pulse < 0.4f)
        pulse = 1.0f;                                   /* a sudden loud hit: the bubbles pop out */
    drift += dt * (0.04 + 0.20 * lvl);

    ui_rgb2hsv(cfg_bar_r, cfg_bar_g, cfg_bar_b, &h0, &s0, &v0);
    s0 = av_clipd(FFMAX(s0, 0.55), 0.0, 1.0);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    ui_hsv2rgb(h0, s0 * 0.8, 0.05 + 0.08 * lvl + 0.10 * pulse, &c);
    SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, 255);
    bg.x = 0;
    bg.y = 0;
    bg.w = W;
    bg.h = H;
    SDL_RenderFillRect(renderer, &bg);

    m = FFMIN(W, H);
    for (i = 0; i < NB; i++) {
        double r1 = fmod(i * 0.61803398875, 1.0);
        double r2 = fmod(i * 0.38196601125 + 0.17, 1.0);
        double r3 = fmod(i * 0.7548776662, 1.0);
        double life = fmod(drift * (0.6 + 0.8 * r1) + r2, 1.0);
        double x = W * (0.05 + 0.90 * r3 + 0.04 * sin(t * (0.5 + r1) + i * 1.7));
        double y = H * (1.1 - 1.2 * life);
        double rad = m * (0.05 + 0.09 * r2) * (0.8 + 0.5 * lvl + 0.6 * pulse);
        double alpha = av_clipd(sin(3.14159265 * life) * (0.35 + 0.45 * lvl + 0.30 * pulse), 0.0, 0.85);
        SDL_Vertex *p = &v[i * (NSEG + 1)];

        ui_hsv2rgb(h0 + 0.14 * sin(i * 0.9) + 0.06 * r1 + 0.03 * sin(t * 0.2), s0, 0.95, &c);
        p->position.x = (float)x;
        p->position.y = (float)y;
        p->color = c;
        p->color.a = (Uint8)(alpha * 255);              /* strong in the middle... */
        p->tex_coord.x = 0;
        p->tex_coord.y = 0;
        for (j = 0; j < NSEG; j++) {
            double a = j * 2.0 * 3.14159265 / NSEG;

            p = &v[i * (NSEG + 1) + 1 + j];
            p->position.x = (float)(x + rad * cos(a));
            p->position.y = (float)(y + rad * sin(a));
            p->color = c;
            p->color.a = 0;                             /* ...and gone at the edge: a soft glow */
            p->tex_coord.x = 0;
            p->tex_coord.y = 0;
        }
    }
    SDL_RenderGeometry(renderer, NULL, v, NB * (NSEG + 1), idx, NB * NSEG * 3);
    return 1;
}

static SDL_Texture *ui_make_target(int w, int h)
{
    SDL_Texture *t = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888,
                                       SDL_TEXTUREACCESS_TARGET, FFMAX(w, 1), FFMAX(h, 1));

    if (t)
        SDL_SetTextureScaleMode(t, SDL_ScaleModeLinear);    /* smooth when stretched */
    return t;
}

/* Make sure the textures match the window size */
static void ui_glass_resize(int ww, int wh)
{
    int i;

    if (ui_scene_tex && ww == ui_gw && wh == ui_gh)
        return;
    if (ui_scene_tex)
        SDL_DestroyTexture(ui_scene_tex);
    for (i = 0; i < 4; i++)
        if (ui_blur_tex[i])
            SDL_DestroyTexture(ui_blur_tex[i]);
    ui_scene_tex = ui_make_target(ww, wh);
    for (i = 0; i < 4; i++)
        ui_blur_tex[i] = ui_make_target(ww >> (i + 1), wh >> (i + 1));
    ui_gw = ww;
    ui_gh = wh;
}

/* Shrink the picture step by step (each step averages 2x2 pixels). That is the blur. */
static void ui_glass_blur(void)
{
    SDL_Texture *from = ui_scene_tex;
    int i;

    for (i = 0; i < 4; i++) {
        if (!ui_blur_tex[i])
            break;
        SDL_SetRenderTarget(renderer, ui_blur_tex[i]);
        SDL_RenderCopy(renderer, from, NULL, NULL);
        from = ui_blur_tex[i];
    }
    SDL_SetRenderTarget(renderer, NULL);
}

/* Copy the blurred picture into one area (the blurred picture covers the whole window) */
static void ui_blur_strip(int x, int y, int w, int h)
{
    SDL_Rect clip, whole;

    if (w <= 0 || h <= 0 || !ui_blur_tex[3])
        return;
    clip.x = x;
    clip.y = y;
    clip.w = w;
    clip.h = h;
    whole.x = 0;
    whole.y = 0;
    whole.w = ui_gw;
    whole.h = ui_gh;
    SDL_RenderSetClipRect(renderer, &clip);
    SDL_RenderCopy(renderer, ui_blur_tex[3], NULL, &whole);
    SDL_RenderSetClipRect(renderer, NULL);
}

/* Frosted glass: a soft shadow, the blurred picture behind a rounded rectangle, a dark tint,
   a faint sheen at the top, a thin inner highlight and a hairline edge. */
static void ui_glass(const SDL_Rect *t, int r)
{
    int row, run = -1, inset, top3, ink = ui_ink_dark;
    SDL_Rect line;

    ui_ink_dark = 0;                            /* the glass itself is drawn as it is */
    r = FFMIN(r, FFMIN(t->w, t->h) / 2);
    ui_shadow(t, r);

    /* 1. The blurred picture, cut to the rounded shape. Full-width rows are
          copied together; the rows in the corners one by one. */
    for (row = 0; row <= t->h; row++) {
        inset = (row < t->h) ? ui_rr_inset(row, t->h, r) : -1;
        if (inset == 0) {
            if (run < 0)
                run = row;
            continue;
        }
        if (run >= 0) {
            ui_blur_strip(t->x, t->y + run, t->w, row - run);
            run = -1;
        }
        if (inset > 0)
            ui_blur_strip(t->x + inset, t->y + row, t->w - 2 * inset, 1);
    }

    /* 2. Tint, sheen, inner highlight and edge */
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    top3 = FFMAX(t->h / 3, 1);
    for (row = 0; row < t->h; row++) {
        inset = ui_rr_inset(row, t->h, r);
        line.x = t->x + inset;
        line.y = t->y + row;
        line.w = t->w - 2 * inset;
        line.h = 1;
        SDL_SetRenderDrawColor(renderer, 225 + cfg_bar_r / 10, 228 + cfg_bar_g / 10, 232 + cfg_bar_b / 10, 168);     /* a light haze */
        SDL_RenderFillRect(renderer, &line);
        if (row < top3) {
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 70 - 70 * row / top3);
            SDL_RenderFillRect(renderer, &line);
        }

    }
    ui_ink_dark = ink;
}

/* The idle background: a few soft glows in the bar color that drift slowly.
   They are drawn tiny and stretched, which makes them smooth. */
static void ui_blobs(void)
{
    SDL_Texture *prev = SDL_GetRenderTarget(renderer);
    double t = av_gettime_relative() / 1000000.0;
    int i, k;

    if (!ui_blob_tex)
        ui_blob_tex = ui_make_target(96, 54);
    if (!ui_blob_tex)
        return;
    SDL_SetRenderTarget(renderer, ui_blob_tex);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
    SDL_SetRenderDrawColor(renderer, 6, 8, 12, 255);
    SDL_RenderClear(renderer);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_ADD);
    for (i = 0; i < 3; i++) {
        int size = 34 + 10 * i;
        int cx = (int)(48 + 30 * sin(t * (0.21 + 0.07 * i) + i * 2.1));
        int cy = (int)(27 + 14 * cos(t * (0.17 + 0.05 * i) + i * 1.3));

        /* several discs on top of each other give a soft glow */
        for (k = 0; k < 16; k++) {
            int d = size * (16 - k) / 16;
            SDL_Rect disc = { cx - d / 2, cy - d / 2, d, d };

            SDL_SetRenderDrawColor(renderer, cfg_bar_r / 36, cfg_bar_g / 36, cfg_bar_b / 36, 255);
            ui_pill(&disc);
        }
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
    SDL_SetRenderTarget(renderer, prev);
    SDL_RenderCopy(renderer, ui_blob_tex, NULL, NULL);
}

/* ----- the Preferences panel ----- */
#define UI_PREF_ROWS 8
#define UI_PREF_ROW ui_pr_row   /* height of one row (smaller in a small window) */
#define UI_PREF_HEAD ui_pr_head /* space for the title */
#define UI_PREF_FOOT ui_pr_foot /* space for the hint at the bottom (none in a small window) */
static int ui_pr_row = 52, ui_pr_head = 76, ui_pr_foot = 52, ui_pr_px = 20, ui_pr_tpx = 28, ui_pr_mg = 32;

static int ui_prefs_open = 0;       /* 1 while the Preferences panel is showing */
static int ui_prefs_hover = -1;     /* row under the mouse */
static double ui_pref_open[UI_PREF_ROWS];   /* 0 to 1: how far each row has changed into its list of choices */
static int ui_prefs_mx = -1, ui_prefs_my = -1;      /* the mouse in the panel (for the choice under it) */
static int ui_prefs_anim = 0;       /* 1 = a row is still gliding */
static double ui_prefs_w = 600.0;   /* the width of the panel: it grows when a row needs more room, and goes back */

static const char *ui_pref_name[UI_PREF_ROWS] = {
    "Seek step", "Volume step", "Hide bars after", "Start fullscreen",
    "Bar color", "Remember volume", "Quit when the queue ends", "Mouse wheel"
};
static const struct { const char *name; int r, g, b; } ui_colors[] = {
    { "Blue", 84, 120, 168 }, { "Teal", 66, 148, 156 }, { "Green", 92, 150, 104 },
    { "Amber", 196, 148, 72 }, { "Red", 196, 84, 84 }, { "Purple", 140, 104, 180 },
    { "Gray", 150, 150, 150 }
};
#define UI_NCOLORS 7
static const av_unused int ui_seek_steps[] = { 1, 2, 3, 5, 10, 15, 30 };
static const int ui_vol_steps[] = { 1, 2, 4, 8, 16 };
static const int ui_hide_steps[] = { 1, 2, 3, 4, 5, 8, 10, 15, 30 };

/* Rows with arrows (the others switch On/Off when clicked) */
static av_unused int ui_pref_arrows(int row)
{
    return row == 0 || row == 1 || row == 2 || row == 4 || row == 7;
}

/* Which color preset is in use? -1 if the color was set by hand in the file */
static int ui_color_index(void)
{
    int i;

    for (i = 0; i < UI_NCOLORS; i++)
        if (ui_colors[i].r == cfg_bar_r && ui_colors[i].g == cfg_bar_g && ui_colors[i].b == cfg_bar_b)
            return i;
    return -1;
}

/* Previous or next number in a list (dir = -1 or 1), starting from the one closest to value */
static int ui_step_list(const int *list, int n, double value, int dir)
{
    int i, best = 0;

    for (i = 1; i < n; i++)
        if (FFABS(list[i] - value) < FFABS(list[best] - value))
            best = i;
    return list[av_clip(best + dir, 0, n - 1)];
}

/* The text shown on the right of a row */
static void ui_pref_value(int row, char *out, size_t size)
{
    int i;

    switch (row) {
    case 0: snprintf(out, size, "%g s", cfg_seek); break;
    case 1: snprintf(out, size, "%d", cfg_vol_step); break;
    case 2: snprintf(out, size, "%g s", cfg_hide_delay / 1000000.0); break;
    case 3: snprintf(out, size, "%s", cfg_fullscreen ? "On" : "Off"); break;
    case 4:
        i = ui_color_index();
        snprintf(out, size, "%s", i >= 0 ? ui_colors[i].name : "Custom");
        break;
    case 5: snprintf(out, size, "%s", cfg_remember_volume ? "On" : "Off"); break;
    case 6: snprintf(out, size, "%s", cfg_quit_when_done ? "On" : "Off"); break;
    default: snprintf(out, size, "%s", cfg_wheel == 1 ? "Volume + queue" : cfg_wheel == 2 ? "Seek + queue" : "Off"); break;
    }
}

/* The choices of a row, for the list that shows when the mouse is on it. Returns how many; sel = the one that is on (or -1) */
static const double ui_seek_choices[] = { 0.3, 0.5, 1, 2, 3, 5, 10, 15, 30 };

static int ui_pref_choices(int row, const char *names[10], char store[10][20], int *sel)
{
    int n = 0, i, b = 0;

    *sel = -1;
    switch (row) {
    case 0:
        for (i = 0; i < 9; i++) {
            snprintf(store[i], 20, "%gs", ui_seek_choices[i]);
            if (fabs(ui_seek_choices[i] - cfg_seek) < fabs(ui_seek_choices[b] - cfg_seek))
                b = i;
        }
        n = 9;
        *sel = b;
        break;
    case 1:
        for (i = 0; i < 5; i++) {
            snprintf(store[i], 20, "%d", ui_vol_steps[i]);
            if (FFABS(ui_vol_steps[i] - cfg_vol_step) < FFABS(ui_vol_steps[b] - cfg_vol_step))
                b = i;
        }
        n = 5;
        *sel = b;
        break;
    case 2:
        for (i = 0; i < 9; i++) {
            snprintf(store[i], 20, "%ds", ui_hide_steps[i]);
            if (fabs(ui_hide_steps[i] - cfg_hide_delay / 1000000.0) < fabs(ui_hide_steps[b] - cfg_hide_delay / 1000000.0))
                b = i;
        }
        n = 9;
        *sel = b;
        break;
    case 4:
        for (i = 0; i < UI_NCOLORS; i++)
            snprintf(store[i], 20, "%s", ui_colors[i].name);
        n = UI_NCOLORS;
        *sel = ui_color_index();
        break;
    case 7:
        snprintf(store[0], 20, "Off");
        snprintf(store[1], 20, "Volume + queue");
        snprintf(store[2], 20, "Seek + queue");
        n = 3;
        *sel = av_clip(cfg_wheel, 0, 2);
        break;
    default:                                    /* the switches: Off and On */
        snprintf(store[0], 20, "Off");
        snprintf(store[1], 20, "On");
        n = 2;
        *sel = (row == 3 ? cfg_fullscreen : row == 5 ? cfg_remember_volume : cfg_quit_when_done) ? 1 : 0;
        break;
    }
    for (i = 0; i < n; i++)
        names[i] = store[i];
    return n;
}

/* Where the choices of a row go: on the right of the name, which stays. The text and the gaps get smaller if they would not
   fit in the room that is left. Returns how many. */
static int ui_pref_layout(int row, const SDL_Rect *p, int cy, SDL_Rect out[10], const char *names[10], char store[10][20],
                          int *sel, int *px)
{
    static const int px_try[4] = { 18, 16, 15, 14 }, pad_try[4] = { 18, 14, 10, 8 };
    int n = ui_pref_choices(row, names, store, sel), i, total = 0, x, w[10], pass, room;

    room = p->w - 2 * ui_pr_mg - ui_text_width(ui_pref_name[row], ui_pr_px) - 18;
    *px = 14;
    for (pass = 0; pass < 4; pass++) {
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], px_try[pass]) + pad_try[pass];
            total += w[i] + (i ? 3 : 0);
        }
        *px = px_try[pass];
        if (total <= room)
            break;
    }
    x = p->x + p->w - ui_pr_mg - total;         /* against the right margin */
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - FFMIN(32, ui_pr_row - 6) / 2;
        out[i].w = w[i];
        out[i].h = FFMIN(32, ui_pr_row - 6);
        x += w[i] + 3;
    }
    return n;
}

/* The width the panel needs so that the name and all choices of a row fit, at the smallest text */
static int ui_pref_need_w(int row)
{
    const char *names[10];
    char store[10][20];
    int sel, n = ui_pref_choices(row, names, store, &sel), i, total = 0;

    for (i = 0; i < n; i++)
        total += ui_text_width(names[i], 14) + 8 + (i ? 3 : 0);
    return 2 * ui_pr_mg + ui_text_width(ui_pref_name[row], ui_pr_px) + 18 + total;
}

/* Which choice of the row is at x, y? -1 if none (or if the choices are not showing yet) */
static int ui_pref_chip_at(int row, const SDL_Rect *p, int x, int y)
{
    SDL_Rect r[10];
    const char *names[10];
    char store[10][20];
    int n, i, sel, px, cy = p->y + UI_PREF_HEAD + row * UI_PREF_ROW + UI_PREF_ROW / 2;

    if (row < 0 || row >= UI_PREF_ROWS || ui_pref_open[row] < 0.4)
        return -1;
    n = ui_pref_layout(row, p, cy, r, names, store, &sel, &px);
    for (i = 0; i < n; i++)
        if (x >= r[i].x && x < r[i].x + r[i].w && y >= r[i].y && y < r[i].y + r[i].h)
            return i;
    return -1;
}

/* Pick choice number idx of a row and save the file */
static void ui_pref_choose(int row, int idx)
{
    switch (row) {
    case 0: cfg_seek = ui_seek_choices[av_clip(idx, 0, 8)]; break;
    case 1: cfg_vol_step = ui_vol_steps[av_clip(idx, 0, 4)]; break;
    case 2: cfg_hide_delay = (int64_t)ui_hide_steps[av_clip(idx, 0, 8)] * 1000000; break;
    case 3: cfg_fullscreen = idx != 0; break;
    case 4:
        idx = av_clip(idx, 0, UI_NCOLORS - 1);
        cfg_bar_r = ui_colors[idx].r;
        cfg_bar_g = ui_colors[idx].g;
        cfg_bar_b = ui_colors[idx].b;
        break;
    case 5: cfg_remember_volume = idx != 0; break;
    case 6: cfg_quit_when_done = idx != 0; break;
    default: cfg_wheel = av_clip(idx, 0, 2); break;
    }
    settings_save();
}

/* Change a setting (dir = -1 or 1 for the arrows) and save the file */
static av_unused void ui_pref_change(int row, int dir)
{
    int i;

    switch (row) {
    case 0: {
        static const double st[] = { 0.3, 0.5, 1, 2, 3, 5, 10, 15, 30 };
        int b = 0, k;

        for (k = 1; k < 9; k++)
            if (fabs(st[k] - cfg_seek) < fabs(st[b] - cfg_seek))
                b = k;
        cfg_seek = st[av_clip(b + dir, 0, 8)];
        break;
    }
    case 1: cfg_vol_step = ui_step_list(ui_vol_steps, 5, cfg_vol_step, dir); break;
    case 2:
        cfg_hide_delay = (int64_t)ui_step_list(ui_hide_steps, 9, cfg_hide_delay / 1000000.0, dir) * 1000000;
        break;
    case 3: cfg_fullscreen = !cfg_fullscreen; break;
    case 4:
        i = (ui_color_index() + dir + UI_NCOLORS) % UI_NCOLORS;
        cfg_bar_r = ui_colors[i].r;
        cfg_bar_g = ui_colors[i].g;
        cfg_bar_b = ui_colors[i].b;
        break;
    case 5: cfg_remember_volume = !cfg_remember_volume; break;
    case 6: cfg_quit_when_done = !cfg_quit_when_done; break;
    default: cfg_wheel = (cfg_wheel + dir + 3) % 3; break;
    }
    settings_save();
}

static SDL_Rect ui_prefs_rect(int ww, int wh)
{
    SDL_Rect p;
    int avail = wh - 16;

    if (avail >= 76 + UI_PREF_ROWS * 52 + 52) {         /* room enough: the full size */
        ui_pr_head = 76;
        ui_pr_row = 52;
        ui_pr_foot = 52;
        ui_pr_px = 20;
        ui_pr_tpx = 28;
    } else if (avail >= 40 + UI_PREF_ROWS * 34) {       /* a shorter window: smaller rows, no hint */
        ui_pr_head = 40;
        ui_pr_foot = 0;
        ui_pr_row = av_clip((avail - 40) / UI_PREF_ROWS, 34, 52);
        ui_pr_px = ui_pr_row >= 40 ? 20 : 17;
        ui_pr_tpx = 22;
    } else {                                            /* a very small window */
        ui_pr_head = 30;
        ui_pr_foot = 0;
        ui_pr_row = FFMAX((avail - 30) / UI_PREF_ROWS, 22);
        ui_pr_px = 14;
        ui_pr_tpx = 18;
    }
    ui_pr_mg = ww < 560 ? 14 : 32;
    p.w = FFMIN((int)(ui_prefs_w + 0.5), ww - 16);
    p.h = UI_PREF_HEAD + UI_PREF_ROWS * UI_PREF_ROW + UI_PREF_FOOT;
    p.x = (ww - p.w) / 2;
    p.y = FFMAX((wh - p.h) / 2, 4);
    return p;
}

static void ui_prefs_draw(void)
{
    SDL_Rect p, sw;
    char value[48];
    int ww, wh, i, cy, x_right, vw, vx;
    double e, se, k, dt, wt;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();

    if (!ui_prefs_open) {
        for (i = 0; i < UI_PREF_ROWS; i++)
            ui_pref_open[i] = 0.0;
        ui_prefs_anim = 0;
        ui_prefs_w = 600.0;
        return;
    }
    dt = now - last > 100000 ? 0.016 : (now - last) / 1000000.0;
    last = now;
    ui_prefs_anim = 0;
    for (i = 0; i < UI_PREF_ROWS; i++) {        /* the rows glide toward their choices, or back */
        double tgt = i == ui_prefs_hover ? 1.0 : 0.0;

        ui_pref_open[i] += (tgt - ui_pref_open[i]) * (1.0 - exp(-dt / 0.07));
        if (fabs(tgt - ui_pref_open[i]) < 0.005)
            ui_pref_open[i] = tgt;
        else
            ui_prefs_anim = 1;
    }
    SDL_GetWindowSize(window, &ww, &wh);
    wt = 600.0;                                 /* the panel grows if the name and the choices of the row under the mouse need more */
    if (ui_prefs_hover >= 0 && ui_prefs_hover < UI_PREF_ROWS)
        wt = FFMAX(wt, ui_pref_need_w(ui_prefs_hover));
    wt = FFMIN(wt, ww - 16);
    ui_prefs_w += (wt - ui_prefs_w) * (1.0 - exp(-dt / 0.09));
    if (fabs(wt - ui_prefs_w) < 0.6)
        ui_prefs_w = wt;
    else
        ui_prefs_anim = 1;
    p = ui_prefs_rect(ww, wh);
    ui_glass(&p, 28);
    x_right = p.x + p.w - ui_pr_mg;

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    ui_label(p.x + ui_pr_mg, p.y + UI_PREF_HEAD / 2 + 4, "Preferences", ui_pr_tpx, 245, 245, 245, 255);
    for (i = 0; i < UI_PREF_ROWS; i++) {
        cy = p.y + UI_PREF_HEAD + i * UI_PREF_ROW + UI_PREF_ROW / 2;
        e = ui_pref_open[i];
        se = e * e * (3.0 - 2.0 * e);
        k = 1.0 - se;                           /* how much of the value is still showing */
        ui_label(p.x + ui_pr_mg, cy, ui_pref_name[i], ui_pr_px, 245, 245, 245, i == ui_prefs_hover ? 255 : 210);     /* the name stays */

        if (k > 0.01) {
            ui_pref_value(i, value, sizeof(value));
            vw = ui_text_width(value, ui_pr_px);
            vx = x_right - vw;
            if (i == 4) {
                sw.x = vx - 26;                 /* a dot in the chosen color */
                sw.y = cy - 8;
                sw.w = 16;
                sw.h = 16;
                SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(255 * k));
                ui_pill(&sw);
            }
            if (!ui_pref_arrows(i) && !strcmp(value, "Off"))
                ui_label(vx, cy, value, ui_pr_px, 150, 150, 150, (int)(255 * k));
            else
                ui_label(vx, cy, value, ui_pr_px, 245, 245, 245, (int)(255 * k));
        }

        if (e > 0.01) {                         /* the choices squeeze in from the right margin, beside the name */
            SDL_Rect r[10];
            const char *names[10];
            char store[10][20];
            int n, c, sel, px, hot;

            n = ui_pref_layout(i, &p, cy, r, names, store, &sel, &px);
            for (c = 0; c < n; c++) {
                double cxc = r[c].x + r[c].w / 2.0, cx = x_right + (cxc - x_right) * se;

                hot = i == ui_prefs_hover && ui_prefs_mx >= r[c].x && ui_prefs_mx < r[c].x + r[c].w &&
                      ui_prefs_my >= r[c].y && ui_prefs_my < r[c].y + r[c].h;
                if (hot) {                      /* a soft pill under the choice the mouse is on */
                    SDL_Rect pill = r[c];

                    pill.x = (int)(cx - r[c].w / 2.0);
                    SDL_SetRenderDrawColor(renderer, 255, 255, 255, (int)(34 * se));
                    ui_pill(&pill);
                }
                if (c == sel)                   /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, names[c], px, av_clip(cfg_bar_r + 40, 0, 255),
                               av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, names[c], px, 245, 245, 245, (int)((hot ? 255 : 170) * se));
            }
        }
    }
    if (UI_PREF_FOOT >= 30)
        ui_label(p.x + ui_pr_mg, p.y + p.h - UI_PREF_FOOT / 2, "Move the mouse onto a setting to see its choices.  Esc closes.",
             15, 170, 170, 170, 255);
}

/* Mouse events while the panel is open. It uses every mouse event. */
static int ui_prefs_mouse(VideoState *is, SDL_Event *ev)
{
    SDL_Rect p;
    int ww, wh, x, y, row;

    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_prefs_rect(ww, wh);
    x = (ev->type == SDL_MOUSEMOTION) ? ev->motion.x : ev->button.x;
    y = (ev->type == SDL_MOUSEMOTION) ? ev->motion.y : ev->button.y;
    row = (y >= p.y + UI_PREF_HEAD) ? (y - p.y - UI_PREF_HEAD) / UI_PREF_ROW : -1;
    if (row >= UI_PREF_ROWS || x < p.x || x >= p.x + p.w)
        row = -1;
    ui_wake();
    ui_prefs_mx = x;
    ui_prefs_my = y;

    if (ev->type == SDL_MOUSEMOTION) {
        ui_prefs_hover = row;
    } else if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT || x < p.x || x >= p.x + p.w ||
            y < p.y || y >= p.y + p.h) {
            ui_prefs_open = 0;                  /* right-click or a click outside closes it */
        } else if (row >= 0) {
            int c = ui_pref_chip_at(row, &p, x, y);

            if (c >= 0)
                ui_pref_choose(row, c);         /* one of the choices of the row */
        }
    }
    if (is)
        is->force_refresh = 1;
    return 1;
}

/* Draw one whole frame with frosted glass: used while a menu or the Preferences panel is up,
   and always on the idle screen. is = the stream playing, or NULL on the idle screen. */
static void ui_glass_frame(VideoState *is)
{
    int ww, wh;

    SDL_GetWindowSize(window, &ww, &wh);
    ui_glass_resize(ww, wh);

    /* Draw the picture into a texture first, so it can be blurred for the glass */
    if (ui_scene_tex)
        SDL_SetRenderTarget(renderer, ui_scene_tex);
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    ui_live_ok = 0;                             /* set again if a video frame is copied for its tile in this drawing */
    if (!is)
        ui_blobs();
    else if (is->audio_st && is->show_mode != SHOW_MODE_VIDEO)
        video_audio_display(is);
    else if (is->video_st)
        video_image_display(is);
    if (is)
        ui_flow_draw(is);
    if (is)
        ui_draw(is);
    ui_titlebar_draw(is);                       /* on the idle screen too */
    if (ui_scene_tex) {
        SDL_SetRenderTarget(renderer, NULL);
        SDL_RenderCopy(renderer, ui_scene_tex, NULL, NULL);
        if (is || ui_prefs_open || ui_q_open || ui_info_open)
            ui_glass_blur();    /* the idle screen has no glass, so it skips the blur */
    }
    ui_menu_stream = is;
    ui_menu_draw();
    ui_ink_dark = 1;                            /* the preferences are light glass: dark text on them */
    ui_prefs_draw();
    ui_ink_dark = 0;
    ui_present();
}

/* ---- the big logo on the idle screen ---- */
static SDL_Texture *ui_logo_tex = NULL;
static int ui_logo_tried = 0;       /* the file is only looked for once */
static double ui_logo_top = 0.0;    /* where the artwork starts, as a fraction of the picture height */

/* Load ~/.config/ffplay-custom/logo.png with FFmpeg's PNG decoder. NULL if it is missing. */
static SDL_Texture *ui_logo_load(void)
{
    char path[1024];
    const char *home = getenv("HOME");
    AVFormatContext *fmt = NULL;
    AVCodecContext *dec = NULL;
    const AVCodec *codec;
    AVPacket *pkt = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    struct SwsContext *sws = NULL;
    uint8_t *rgba = NULL;
    SDL_Texture *tex = NULL;
    int w, h, ok = 0;

    if (!home || !pkt || !frame)
        goto end;
    snprintf(path, sizeof(path), "%s/.config/ffplay-custom/logo.png", home);
    if (avformat_open_input(&fmt, path, NULL, NULL) < 0)
        goto end;
    if (avformat_find_stream_info(fmt, NULL) < 0 || fmt->nb_streams < 1)
        goto end;
    codec = avcodec_find_decoder(fmt->streams[0]->codecpar->codec_id);
    if (!codec)
        goto end;
    dec = avcodec_alloc_context3(codec);
    if (!dec || avcodec_parameters_to_context(dec, fmt->streams[0]->codecpar) < 0)
        goto end;
    if (avcodec_open2(dec, codec, NULL) < 0)
        goto end;
    if (av_read_frame(fmt, pkt) < 0)
        goto end;
    if (avcodec_send_packet(dec, pkt) < 0)
        goto end;
    if (avcodec_receive_frame(dec, frame) < 0) {
        avcodec_send_packet(dec, NULL);         /* flush, in case the frame is held back */
        if (avcodec_receive_frame(dec, frame) < 0)
            goto end;
    }
    w = frame->width;
    h = frame->height;
    if (w <= 0 || h <= 0 || w > 4096 || h > 4096)
        goto end;

    /* Turn whatever the PNG decoded to into plain RGBA */
    rgba = av_malloc((size_t)w * h * 4);
    sws = sws_getContext(w, h, frame->format, w, h, AV_PIX_FMT_RGBA, SWS_BICUBIC, NULL, NULL, NULL);
    if (!rgba || !sws)
        goto end;
    {
        uint8_t *dst[4] = { rgba, NULL, NULL, NULL };
        int dst_stride[4] = { w * 4, 0, 0, 0 };

        sws_scale(sws, (const uint8_t * const *)frame->data, frame->linesize, 0, h, dst, dst_stride);
    }
    tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, w, h);
    if (!tex)
        goto end;
    SDL_UpdateTexture(tex, NULL, rgba, w * 4);
    {
        /* The top edge of the artwork: the first row with a solid pixel (soft shadows are skipped) */
        int x, y;

        for (y = 0; y < h && ui_logo_top == 0.0; y++)
            for (x = 0; x < w; x++)
                if (rgba[((size_t)y * w + x) * 4 + 3] >= 128) {
                    ui_logo_top = (double)y / h;
                    break;
                }
    }
    SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_BLEND);
#if SDL_VERSION_ATLEAST(2, 0, 12)
    SDL_SetTextureScaleMode(tex, SDL_ScaleModeBest);
#endif
    ok = 1;

end:
    if (!ok && tex) {
        SDL_DestroyTexture(tex);
        tex = NULL;
    }
    sws_freeContext(sws);
    av_free(rgba);
    avcodec_free_context(&dec);
    avformat_close_input(&fmt);
    av_packet_free(&pkt);
    av_frame_free(&frame);
    return tex;
}

/* How big the logo is and how far it sits from the menu, for a window of ww x wh */
static void ui_logo_metrics(int ww, int wh, int *size, int *gap)
{
    int s = av_clip(wh * 36 / 100, 140, 420);

    s = FFMAX(FFMIN(s, ww * 38 / 100), 100);
    *size = s;
    *gap = s * 2 / 5;
}

/* Load the logo the first time it is needed */
static void ui_logo_prepare(void)
{
    if (!ui_logo_tried) {
        ui_logo_tried = 1;
        ui_logo_tex = ui_logo_load();
    }
}

/* Draw the logo centered on (cx, cy). Without a logo.png the round play badge is used. */
static void ui_logo_draw(int cx, int cy, int size)
{
    SDL_Rect dst = { cx - size / 2, cy - size / 2, size, size };

    ui_logo_prepare();
    if (ui_logo_tex)
        SDL_RenderCopy(renderer, ui_logo_tex, NULL, &dst);
    else
        ui_logo(cx, cy, size);
}

/* Where the menu rows are: next to the logo on the idle screen, or at the right-click spot */
static SDL_Rect ui_menu_rect(int ww, int wh)
{
    SDL_Rect r;
    int i, longest = 0;

    ui_menu_rowh = av_clip((wh - 16) / UI_MENU_ITEMS, 30, 44);
    for (i = 0; i < UI_MENU_ITEMS; i++)
        longest = FFMAX(longest, ui_text_width(ui_menu_label[i], 22));
    r.w = longest + 56;
    r.h = UI_MENU_ITEMS * UI_MENU_ROW;
    if (ui_idle) {
        /* big logo + gap + menu, centered in the window */
        int ls, gap;

        ui_logo_metrics(ww, wh, &ls, &gap);
        r.x = (ww - (ls + gap + r.w)) / 2 + ls + gap;
        ui_logo_prepare();
        r.y = wh / 2 - ls / 2 + (int)(ui_logo_top * ls + 0.5) - (UI_MENU_ROW - 16) / 2;
        r.y = FFMAX(r.y, 8);
    } else {
        r.x = av_clip(ui_menu_x, 8, FFMAX(ww - r.w - 8, 8));
        r.y = av_clip(ui_menu_y, 8, FFMAX(wh - r.h - 8, 8));
    }
    return r;
}

/* Draw the menu (and the logo on the idle screen). Does nothing if neither is showing. */
static void toggle_pause(VideoState *is);

/* ----- the queue panel: opens beside the "Queue" row ----- */
#define UI_Q_W 420              /* panel width */
#define UI_Q_HEAD 52            /* the top row: add, previous, play/pause, next, shuffle */
#define UI_Q_ROW 40             /* one queue item */
#define UI_Q_PAD 10             /* space above and below the rows */
#define UI_Q_FOOT 116           /* under the list: crossfade, sleep timer and the counter */

/* What the mouse is over in the panel */
#define UI_Q_NONE 0
#define UI_Q_ADD  1             /* "Add to queue..." */
#define UI_Q_SHUF 2             /* the shuffle icon */
#define UI_Q_ITEM 3             /* a queue item */
#define UI_Q_DOT  4             /* the drag dot at the end of an item */
#define UI_Q_PREV 5             /* previous */
#define UI_Q_PLAY 6             /* play / pause */
#define UI_Q_NEXT 7             /* next */
#define UI_Q_DEL  8             /* the x that removes an item */
#define UI_Q_XF_DEC 9           /* crossfade: shorter */
#define UI_Q_XF_INC 10          /* crossfade: longer */
#define UI_Q_SLEEP  11          /* the sleep timer row */
#define UI_Q_CHIP   12          /* one of its choices (the number is in the item) */
#define UI_Q_XFCHIP 13          /* one of the choices of the crossfade (the number is in the item) */
#define UI_Q_XFROW  14          /* the crossfade row: its choices show while the mouse is on it */

/* How many items are shown at once (the panel scrolls beyond that) */
static int ui_q_visible(int wh)
{
    int room = (wh - 16 - 2 * UI_Q_PAD - UI_Q_HEAD - UI_Q_FOOT) / UI_Q_ROW;

    return av_clip(FFMAX(q_count, 1), 1, av_clip(room, 1, 14));
}

/* Where the panel is: beside the menu, level with the "Queue" row */
static SDL_Rect ui_q_rect(int ww, int wh)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;

    p.w = FFMIN(FFMIN(UI_Q_W, FFMAX(ww / 3, 360)), ww - 16);
    p.h = 2 * UI_Q_PAD + UI_Q_HEAD + ui_q_visible(wh) * UI_Q_ROW + UI_Q_FOOT;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;                  /* to the right of the menu */
    else
        p.x = FFMAX(m.x - gap - p.w, 8);        /* no room there: to the left */
    p.y = av_clip(m.y + UI_ROW_QUEUE * UI_MENU_ROW - UI_Q_PAD, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

/* The choices of the sleep timer. Chosen with ui_sleep_choose(): 0 = off, 1 = end of track, 2 to 5 = minutes. */
static const char *const ui_chip_full[6] = { "Off", "End of track", "5 min", "10 min", "30 min", "1 hr" };
static const char *const ui_chip_short[6] = { "Off", "End", "5m", "10m", "30m", "1h" };

/* The choices of the crossfade, in seconds */
static const char *const ui_xf_names[7] = { "Off", "1s", "2s", "3s", "5s", "8s", "10s" };
static const int ui_xf_vals[7] = { 0, 1, 2, 3, 5, 8, 10 };

/* Where the choices of a row under the list go: on the right of its name (labelw wide), which stays. The long names are used
   when they fit, then the short ones, then smaller text. Returns the names to draw; *px is their text size. */
static const char *const *ui_q_chips_for(const SDL_Rect *p, int cy, int labelw, int n, const char *const *full,
                                         const char *const *shrt, SDL_Rect *out, int *px)
{
    static const int pxs[3] = { 14, 15, 13 }, pads[3] = { 10, 8, 6 };
    const char *const *names = full;
    int pass, i, w[8], total = 0, x, room = p->w - 40 - labelw - 14;

    for (pass = 0; pass < 3; pass++) {
        names = pass == 0 ? full : shrt;
        total = 0;
        for (i = 0; i < n; i++) {
            w[i] = ui_text_width(names[i], pxs[pass]) + pads[pass];
            total += w[i] + (i ? 3 : 0);
        }
        *px = pxs[pass];
        if (total <= room)
            break;
    }
    x = p->x + p->w - 20 - total;
    for (i = 0; i < n; i++) {
        out[i].x = x;
        out[i].y = cy - 13;
        out[i].w = w[i];
        out[i].h = 26;
        x += w[i] + 3;
    }
    return names;
}

/* The six choices of the sleep timer (cy = the middle of the row) */
static const char *const *ui_q_chips(const SDL_Rect *p, int cy, SDL_Rect out[6])
{
    int px;

    return ui_q_chips_for(p, cy, ui_text_width("Sleep timer", 18), 6, ui_chip_full, ui_chip_short, out, &px);
}

/* The list position where the dragged item would land */
static int ui_q_drop(int wh, const SDL_Rect *p)
{
    int top = p->y + UI_Q_PAD + UI_Q_HEAD;
    int slot = av_clip((ui_q_drag_y - top) / UI_Q_ROW, 0, ui_q_visible(wh) - 1);

    return av_clip(ui_q_scroll + slot, 0, FFMAX(q_count - 1, 0));
}

/* Which item is shown at a list position. While one is dragged, the others make room for it. */
static int ui_q_slot_item(int slot, int drop)
{
    int k;

    if (ui_q_drag < 0)
        return slot;
    if (slot == drop)
        return ui_q_drag;
    k = slot < drop ? slot : slot - 1;          /* position without the dragged item */
    return k < ui_q_drag ? k : k + 1;
}

/* What is at (x, y) in the panel? item = the queue item for ITEM, DOT and DEL, or the choice for CHIP. */
static int ui_q_hit(const SDL_Rect *p, int wh, int x, int y, int *item)
{
    int top = p->y + UI_Q_PAD + UI_Q_HEAD, slot, drop = 0, right = p->x + p->w;
    int fy = top + ui_q_visible(wh) * UI_Q_ROW, i;
    SDL_Rect chip[8];

    *item = -1;
    if (x < p->x || x >= right || y < p->y || y >= p->y + p->h)
        return UI_Q_NONE;
    if (y < top) {                              /* the top row */
        if (y < p->y + UI_Q_PAD)
            return UI_Q_NONE;
        if (x >= right - 56)
            return UI_Q_SHUF;
        if (x >= right - 96)
            return UI_Q_NEXT;
        if (x >= right - 136)
            return UI_Q_PLAY;
        if (x >= right - 176)
            return UI_Q_PREV;
        return UI_Q_ADD;
    }
    if (y >= fy) {                              /* under the list */
        if (y >= fy + 6 && y < fy + 46) {       /* crossfade: the choices are there while the mouse is on the row */
            if (ui_q_hover_kind == UI_Q_XFROW || ui_q_hover_kind == UI_Q_XFCHIP) {
                int xpx;

                ui_q_chips_for(p, fy + 26, ui_text_width("Crossfade", 18), 7, ui_xf_names, ui_xf_names, chip, &xpx);
                for (i = 0; i < 7; i++)
                    if (x >= chip[i].x && x < chip[i].x + chip[i].w) {
                        *item = i;
                        return UI_Q_XFCHIP;
                    }
            }
            return UI_Q_XFROW;
        }
        if (y >= fy + 46 && y < fy + 86) {      /* sleep timer */
            if (ui_q_hover_kind == UI_Q_SLEEP || ui_q_hover_kind == UI_Q_CHIP) {    /* the choices are showing */
                ui_q_chips(p, fy + 66, chip);
                for (i = 0; i < 6; i++)
                    if (x >= chip[i].x && x < chip[i].x + chip[i].w) {
                        *item = i;
                        return UI_Q_CHIP;
                    }
            }
            return UI_Q_SLEEP;
        }
        return UI_Q_NONE;
    }
    slot = (y - top) / UI_Q_ROW;
    if (slot >= ui_q_visible(wh) || ui_q_scroll + slot >= q_count)
        return UI_Q_NONE;
    if (ui_q_drag >= 0)
        drop = ui_q_drop(wh, p);
    *item = ui_q_slot_item(ui_q_scroll + slot, drop);
    if (x >= right - 48)
        return UI_Q_DOT;
    if (x >= right - 86)
        return UI_Q_DEL;
    return UI_Q_ITEM;
}

/* Should a panel stay open with the mouse here? The panel, plus the gap to its menu row. */
static int ui_q_keep(const SDL_Rect *m, const SDL_Rect *p, int x, int y, int row)
{
    int row_top = m->y + row * UI_MENU_ROW;
    int x0 = p->x >= m->x ? m->x + m->w : p->x + p->w;
    int x1 = p->x >= m->x ? p->x : m->x;

    if (x >= p->x - 6 && x < p->x + p->w + 6 && y >= p->y - 6 && y < p->y + p->h + 6)
        return 1;
    return x >= x0 && x < x1 && y >= row_top - 6 && y < row_top + UI_MENU_ROW + 6;
}

/* Is this text (the inside of a bracket) only download or codec information, like 1080p_25fps_H264? */
static int ui_q_is_codec_info(const char *s)
{
    int n = 0;

    while (av_isdigit(s[n]))
        n++;
    if (n >= 3 && s[n] == 'p')                  /* 720p, 1080p, 1440p, 2160p ... */
        return 1;
    return n >= 2 && !strncmp(s + n, "kbit", 4);        /* 128kbit ... */
}

/* The name shown for a queue item: the file name without its folder, its extension
   and any trailing "(1080p_25fps_H264-128kbit_AAC)" */
static void ui_q_name(int idx, char *out, size_t size)
{
    const char *s = q_items[idx];
    const char *slash = strrchr(s, '/');
    char *dot, *open;
    size_t len;

    snprintf(out, size, "%s", slash ? slash + 1 : s);
    dot = strrchr(out, '.');
    if (dot && dot != out && strlen(dot) <= 5)
        *dot = 0;
    for (;;) {
        len = strlen(out);
        while (len > 0 && out[len - 1] == ' ')
            out[--len] = 0;
        open = strrchr(out, '(');
        if (!open || open == out || len == 0 || out[len - 1] != ')' || !ui_q_is_codec_info(open + 1))
            break;
        *open = 0;
    }
}

/* Cut a text so it fits in max_w pixels, ending with "...". s needs room for 4 more bytes. */
static void ui_fit_text(char *s, int px, int max_w)
{
    char tmp[320];
    int len = (int)strlen(s);
    int w = ui_text_width(s, px);
    int keep;

    if (w <= max_w || len < 2)
        return;
    keep = FFMIN((int)((int64_t)len * max_w / w), len - 1);
    for (; keep > 0; keep--) {
        if ((s[keep] & 0xC0) == 0x80)
            continue;                           /* inside a multi-byte character */
        memcpy(tmp, s, keep);
        memcpy(tmp + keep, "...", 4);
        if (ui_text_width(tmp, px) <= max_w)
            break;
    }
    if (keep > 0)
        memcpy(s, tmp, keep + 4);
    else
        memcpy(s, "...", 4);
}

/* A line about 2 pixels thick */
static void ui_q_line(int x0, int y0, int x1, int y1)
{
    SDL_RenderDrawLine(renderer, x0, y0, x1, y1);
    SDL_RenderDrawLine(renderer, x0 + 1, y0, x1 + 1, y1);
    SDL_RenderDrawLine(renderer, x0, y0 + 1, x1, y1 + 1);
}

/* A smooth curve, drawn as 16 short lines */
static void ui_bezier(double x0, double y0, double x1, double y1, double x2, double y2, double x3, double y3)
{
    double px = x0, py = y0;
    int i;

    for (i = 1; i <= 16; i++) {
        double t = i / 16.0, u = 1.0 - t;
        double x = u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3;
        double y = u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3;

        ui_q_line((int)(px + 0.5), (int)(py + 0.5), (int)(x + 0.5), (int)(y + 0.5));
        px = x;
        py = y;
    }
}

/* A filled triangle with its flat side at x (pointing right, dir = 1) or at x + w (pointing left) */
static void ui_tri(int x, int cy, int w, int h, int dir)
{
    int row;

    for (row = 0; row < h; row++) {
        double d = (row < h / 2.0 ? row + 0.5 : h - row - 0.5) / (h / 2.0);
        int len = (int)(w * d + 0.5);
        SDL_Rect line;

        line.y = cy - h / 2 + row;
        line.h = 1;
        line.w = len;
        line.x = dir > 0 ? x : x + w - len;
        SDL_RenderFillRect(renderer, &line);
    }
}

/* The traditional shuffle icon: two curves that cross, with arrow heads on the right */
static void ui_shuffle_icon(int cx, int cy, int r, int g, int b, int a)
{
    SDL_SetRenderDrawColor(renderer, r, g, b, (int)(a * ui_fade));
    ui_bezier(cx - 11, cy - 5, cx + 1, cy - 5, cx - 1, cy + 5, cx + 8, cy + 5);
    ui_bezier(cx - 11, cy + 5, cx + 1, cy + 5, cx - 1, cy - 5, cx + 8, cy - 5);
    ui_tri(cx + 6, cy + 5, 8, 9, 1);
    ui_tri(cx + 6, cy - 5, 8, 9, 1);
}

/* Previous (0), play (1), pause (2) and next (3) */
static void ui_transport_icon(int which, int cx, int cy, int a)
{
    SDL_Rect bar;

    SDL_SetRenderDrawColor(renderer, 230, 230, 230, (int)(a * ui_fade));
    if (which == 0) {
        ui_tri(cx - 11, cy, 10, 14, -1);
        ui_tri(cx - 1, cy, 10, 14, -1);
    } else if (which == 3) {
        ui_tri(cx - 9, cy, 10, 14, 1);
        ui_tri(cx + 1, cy, 10, 14, 1);
    } else if (which == 1) {
        ui_tri(cx - 5, cy, 12, 14, 1);
    } else {
        bar.y = cy - 7;
        bar.w = 4;
        bar.h = 14;
        bar.x = cx - 6;
        SDL_RenderFillRect(renderer, &bar);
        bar.x = cx + 2;
        SDL_RenderFillRect(renderer, &bar);
    }
}

/* The arrow at the end of a menu row that opens a panel */
static void ui_chevron(int x, int cy, int a)
{
    ui_arrow(x + 3, cy, 1, a - 60);
}

/* Choose what the sleep timer does: 0 = off, 1 = stop after the item that plays now, 2 to 5 = in 5, 10, 30
   or 60 minutes (the sound fades out over the last 20 seconds, then playback pauses) */
static void ui_sleep_choose(int sel)
{
    static const int minutes[6] = { 0, 0, 5, 10, 30, 60 };

    q_sleep_item = NULL;
    q_sleep_end = 0;
    ui_sleep_gain = 1.0f;
    ui_sleep_sel = 0;
    if (sel == 1 && q_pos >= 0 && q_pos < q_count) {
        q_sleep_item = q_items[q_pos];
        ui_sleep_sel = 1;
    } else if (sel >= 2 && sel <= 5) {
        q_sleep_end = av_gettime_relative() + (int64_t)minutes[sel] * 60 * 1000000;
        ui_sleep_sel = sel;
    }
}

/* The choice that is on now (0 to 5) */
static int ui_sleep_current(void)
{
    if (q_sleep_end)
        return av_clip(ui_sleep_sel, 2, 5);
    return q_sleep_item ? 1 : 0;
}

/* What the sleep row says while it is closed */
static void ui_sleep_text(char *out, size_t size)
{
    int i, left;

    if (q_sleep_end) {
        left = (int)((q_sleep_end - av_gettime_relative() + 999999) / 1000000);
        snprintf(out, size, "%d:%02d left", FFMAX(left, 0) / 60, FFMAX(left, 0) % 60);
    } else if (q_sleep_item) {
        for (i = 0; i < q_count; i++)
            if (q_items[i] == q_sleep_item)
                break;
        if (i == q_pos || i >= q_count)
            snprintf(out, size, "End of track");
        else
            snprintf(out, size, "After item %d", i + 1);
    } else {
        snprintf(out, size, "Off");
    }
}

/* h:mm:ss, or m:ss when the hours are not needed */
static void ui_fmt_clock(char *out, size_t size, double s, int hours)
{
    int t = (int)(s + 0.5);

    if (t < 0)
        t = 0;
    if (hours)
        snprintf(out, size, "%d:%02d:%02d", t / 3600, t / 60 % 60, t % 60);
    else
        snprintf(out, size, "%d:%02d", t / 60, t % 60);
}

/* How far the fade-in of row number i of the queue panel has got (0 to 1, easing out). The rows start
   one after another; the last ones do not wait longer than a third of a second. */
static double ui_cascade(int i)
{
    double k;

    if (ui_q_drag >= 0)
        return 1.0;
    k = av_clipd((av_gettime_relative() - ui_q_anim_t0 - FFMIN(i * 24000, 300000)) / 170000.0, 0.0, 1.0);
    return 1.0 - (1.0 - k) * (1.0 - k) * (1.0 - k);
}

static void ui_q_draw(int ww, int wh)
{
    static int64_t stats_at = 0;
    static double st_before = 0, st_total = 0;
    static int st_unknown = 0, st_gen = -1;
    SDL_Rect p = ui_q_rect(ww, wh), sep, dot, clip;
    char name[300], text[96], a[24], b[24];
    int vis = ui_q_visible(wh);
    int top = p.y + UI_Q_PAD + UI_Q_HEAD;
    int right = p.x + p.w;
    int max_w = p.w - 20 - 94;
    int drop = 0, i, item, cy, lit, hk = ui_q_hover_kind, fy, marker, sel;
    int paused = ui_menu_stream && ui_menu_stream->paused;
    int64_t now = av_gettime_relative();
    double cur = 0, c;

    if (ui_q_reveal) {              /* just opened: show the playing item with two items above it */
        ui_q_scroll = q_pos - 2;
        ui_q_reveal = 0;
        ui_q_last_scroll = -1;          /* just opened: no gliding, show it in place */
    }
    ui_q_scroll = av_clip(ui_q_scroll, 0, FFMAX(q_count - vis, 0));
    {                                   /* the rows scrolled since the last drawing slide into place */
        double ddt = ui_q_off_t ? av_clipd((now - ui_q_off_t) / 1000000.0, 0.0, 0.1) : 0.0;

        if (ui_q_last_scroll < 0)
            ui_q_off = 0.0;
        else
            ui_q_off += ui_q_scroll - ui_q_last_scroll;
        ui_q_last_scroll = ui_q_scroll;
        ui_q_off = av_clipd(ui_q_off, -3.0, 3.0) * exp(-ddt * 14.0);
        if (fabs(ui_q_off) < 0.01)
            ui_q_off = 0.0;
        ui_q_off_t = now;
    }
    if (ui_q_drag >= 0)
        drop = ui_q_drop(wh, &p);
    ui_glass(&p, 22);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);

    ui_fade = ui_cascade(0);
    /* top row: "Add to queue...", previous, play/pause, next and shuffle */
    cy = p.y + UI_Q_PAD + UI_Q_HEAD / 2;
    ui_label(p.x + 20, cy, "Add to queue...", 20, 240, 240, 240, hk == UI_Q_ADD ? 255 : 210);
    ui_transport_icon(0, right - 156, cy, hk == UI_Q_PREV ? 255 : 175);
    ui_transport_icon(paused ? 1 : 2, right - 116, cy, hk == UI_Q_PLAY ? 255 : 175);
    ui_transport_icon(3, right - 76, cy, hk == UI_Q_NEXT ? 255 : 175);
    if (q_shuffle)
        ui_shuffle_icon(right - 36, cy, cfg_bar_r, cfg_bar_g, cfg_bar_b, 255);     /* on: the bar color */
    else
        ui_shuffle_icon(right - 36, cy, 220, 220, 220, hk == UI_Q_SHUF ? 255 : 150);
    sep.x = p.x + 16;
    sep.y = top - 1;
    sep.w = p.w - 32;
    sep.h = 1;
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 40);
    SDL_RenderFillRect(renderer, &sep);

    if (q_count == 0)
        ui_label(p.x + 20, top + UI_Q_ROW / 2, "The queue is empty", 18, 220, 220, 220, 150);

    clip.x = p.x;
    clip.y = top;
    clip.w = p.w;
    clip.h = vis * UI_Q_ROW;
    SDL_RenderSetClipRect(renderer, &clip);     /* rows slide in and out at the list's edges */
    for (i = -1; i <= vis && ui_q_scroll + i < q_count; i++) {
        if (ui_q_scroll + i < 0)
            continue;
        item = ui_q_slot_item(ui_q_scroll + i, drop);
        cy = top + (int)((i + ui_q_off) * UI_Q_ROW) + UI_Q_ROW / 2;
        ui_fade = ui_cascade(FFMAX(i, 0) + 1);
        lit = ui_q_drag < 0 && item == ui_q_hover_idx &&
              (hk == UI_Q_ITEM || hk == UI_Q_DOT || hk == UI_Q_DEL);
        marker = q_items[item] == q_sleep_item;
        ui_q_name(item, name, 290);
        ui_fit_text(name, 18, max_w - (marker ? 28 : 0));
        if (item == q_pos || item == ui_q_drag)
            ui_label(p.x + 20 + (int)((1.0 - ui_fade) * 12), cy, name, 18, av_clip(cfg_bar_r + 40, 0, 255),
                     av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), 255);
        else
            ui_label(p.x + 20 + (int)((1.0 - ui_fade) * 12), cy, name, 18, 240, 240, 240, lit ? 255 : 205);
        if (marker)                 /* playback stops after this item */
            ui_label(right - 120, cy, "Zz", 15, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                     av_clip(cfg_bar_b + 40, 0, 255), 230);

        /* the x that removes the item */
        SDL_SetRenderDrawColor(renderer, 230, 230, 230, (int)(((lit && hk == UI_Q_DEL) ? 255 : 120) * ui_fade));
        ui_q_line(right - 71, cy - 4, right - 63, cy + 4);
        ui_q_line(right - 71, cy + 4, right - 63, cy - 4);

        /* the dot to drag by: the bar color for the playing item and the one being dragged */
        dot.w = 10;
        dot.h = 10;
        dot.x = right - 30;
        dot.y = cy - 5;
        if (item == q_pos || item == ui_q_drag)
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(255 * ui_fade));
        else
            SDL_SetRenderDrawColor(renderer, 200, 200, 200, (int)((lit ? 200 : 120) * ui_fade));
        ui_pill(&dot);
    }

    SDL_RenderSetClipRect(renderer, NULL);

    /* under the list */
    fy = top + vis * UI_Q_ROW;
    sep.x = p.x + 16;
    sep.y = fy + 3;
    sep.w = p.w - 32;
    sep.h = 1;
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 40);
    SDL_RenderFillRect(renderer, &sep);

    ui_fade = ui_cascade(vis + 1);
    /* crossfade: its name stays; the choices squeeze in on the right of it while the mouse is on the row */
    cy = fy + 26;
    {
        double tgt = (hk == UI_Q_XFROW || hk == UI_Q_XFCHIP) ? 1.0 : 0.0, se, ek, dt, hx = right - 20;
        int64_t t2 = av_gettime_relative();
        SDL_Rect xr[8];
        const char *const *xn;
        int xpx, cur = 0, k;

        dt = t2 - ui_xf_last > 100000 ? 0.016 : (t2 - ui_xf_last) / 1000000.0;
        ui_xf_last = t2;
        ui_xf_e += (tgt - ui_xf_e) * (1.0 - exp(-dt / 0.07));
        if (fabs(tgt - ui_xf_e) < 0.005)
            ui_xf_e = tgt;
        ui_xf_anim = ui_xf_e != tgt;
        se = ui_xf_e * ui_xf_e * (3.0 - 2.0 * ui_xf_e);
        ek = 1.0 - se;
        ui_label(p.x + 20, cy, "Crossfade", 18, 240, 240, 240, 210);
        if (ek > 0.01) {
            if (cfg_crossfade)
                snprintf(text, sizeof(text), "%d s", cfg_crossfade);
            else
                snprintf(text, sizeof(text), "Off");
            if (cfg_crossfade)
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 245, 245, 245, (int)(255 * ek));
            else
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 150, 150, 150, (int)(255 * ek));
        }
        if (ui_xf_e > 0.01) {
            for (k = 1; k < 7; k++)
                if (abs(ui_xf_vals[k] - cfg_crossfade) < abs(ui_xf_vals[cur] - cfg_crossfade))
                    cur = k;
            xn = ui_q_chips_for(&p, cy, ui_text_width("Crossfade", 18), 7, ui_xf_names, ui_xf_names, xr, &xpx);
            for (k = 0; k < 7; k++) {
                int hot = hk == UI_Q_XFCHIP && ui_q_hover_idx == k;
                double cxc = xr[k].x + xr[k].w / 2.0, cx = hx + (cxc - hx) * se;

                if (k == cur)
                    ui_label_c((int)cx, cy, xn[k], xpx, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, xn[k], xpx, 245, 245, 245, (int)((hot ? 255 : 160) * se));
            }
        }
    }

    /* sleep timer: its name stays; the choices squeeze in on the right of it while the mouse is on the row */
    cy = fy + 66;
    sel = ui_sleep_current();
    {
        double tgt = (hk == UI_Q_SLEEP || hk == UI_Q_CHIP) ? 1.0 : 0.0, ek, se, dt, hx = right - 20;
        int64_t t2 = av_gettime_relative();
        SDL_Rect sr[8];
        const char *const *sn;
        int spx;

        dt = t2 - ui_chip_last > 100000 ? 0.016 : (t2 - ui_chip_last) / 1000000.0;
        ui_chip_last = t2;
        ui_chip_e += (tgt - ui_chip_e) * (1.0 - exp(-dt / 0.07));      /* the row glides, it does not jump */
        if (fabs(tgt - ui_chip_e) < 0.005)
            ui_chip_e = tgt;
        ui_chip_anim = ui_chip_e != tgt;
        se = ui_chip_e * ui_chip_e * (3.0 - 2.0 * ui_chip_e);
        ek = 1.0 - se;
        ui_label(p.x + 20, cy, "Sleep timer", 18, 240, 240, 240, 210);
        if (ek > 0.01) {
            ui_sleep_text(text, sizeof(text));
            if (sel)
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, av_clip(cfg_bar_r + 40, 0, 255),
                         av_clip(cfg_bar_g + 40, 0, 255), av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * ek));
            else
                ui_label(right - 20 - ui_text_width(text, 18), cy, text, 18, 150, 150, 150, (int)(255 * ek));
        }
        if (ui_chip_e > 0.01) {
            sn = ui_q_chips_for(&p, cy, ui_text_width("Sleep timer", 18), 6, ui_chip_full, ui_chip_short, sr, &spx);
            for (i = 0; i < 6; i++) {
                int hot = hk == UI_Q_CHIP && ui_q_hover_idx == i;
                double cxc = sr[i].x + sr[i].w / 2.0, cx = hx + (cxc - hx) * se;

                if (i == sel)               /* the choice that is on: in the bar color */
                    ui_label_c((int)cx, cy, sn[i], spx, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(255 * se));
                else
                    ui_label_c((int)cx, cy, sn[i], spx, 245, 245, 245, (int)((hot ? 255 : 160) * se));
            }
        }
    }

    /* the counter: which item, and how far through the whole queue. Quiet on purpose. */
    if (st_gen != q_dur_gen || now - stats_at > 400000 || now < stats_at) {
        st_gen = q_dur_gen;
        queue_stats(ui_menu_stream != NULL, &st_before, &st_total, &st_unknown);
        stats_at = now;
    }
    if (ui_menu_stream) {
        c = get_master_clock(ui_menu_stream);
        if (!isnan(c)) {
            cur = c;
            if (ui_menu_stream->ic && ui_menu_stream->ic->start_time != AV_NOPTS_VALUE)
                cur -= ui_menu_stream->ic->start_time / (double)AV_TIME_BASE;
        }
    }
    ui_fmt_clock(a, sizeof(a), st_before + FFMAX(cur, 0), st_total >= 3600);
    ui_fmt_clock(b, sizeof(b), st_total, st_total >= 3600);
    snprintf(text, sizeof(text), "%d/%d   [%s / %s%s]", FFMAX(q_pos + 1, 0), q_count, a, b, st_unknown ? "+" : "");
    ui_label_c(p.x + p.w / 2, fy + 100, text, 15, 170, 170, 170, 255);
    ui_fade = 1.0;
}

/* ----- the Media Info panel: opens beside the "Media Info" row ----- */
#define UI_I_ROW 30             /* height of one line */
#define UI_I_PAD 14             /* space above and below the lines */
#define UI_INFO_MAX 24
static char ui_il_label[UI_INFO_MAX][16];
static char ui_il_value[UI_INFO_MAX][200];

static void ui_info_put(int *n, const char *label, const char *value)
{
    if (*n >= UI_INFO_MAX || !value || !*value)
        return;
    snprintf(ui_il_label[*n], sizeof(ui_il_label[0]), "%s", label);
    snprintf(ui_il_value[*n], sizeof(ui_il_value[0]), "%s", value);
    (*n)++;
}

/* A codec name with its profile, like "aac (LC)" */
static void ui_info_codec(char *out, size_t size, enum AVCodecID id, int profile)
{
    const char *prof = avcodec_profile_name(id, profile);

    if (prof)
        snprintf(out, size, "%s (%s)", avcodec_get_name(id), prof);
    else
        snprintf(out, size, "%s", avcodec_get_name(id));
}

/* Collect what is known about the file that is playing. Returns the number of lines. */
static int ui_info_collect(VideoState *is)
{
    static const char *const tags[5][2] = {
        { "title", "Title" }, { "artist", "Artist" }, { "album", "Album" },
        { "date", "Date" }, { "genre", "Genre" }
    };
    AVFormatContext *ic;
    AVDictionaryEntry *e;
    AVCodecParameters *par;
    AVRational fr;
    const char *pf;
    char v[200];
    int n = 0, i;
    int64_t s;

    if (!is || !(ic = is->ic))
        return 0;
    for (i = 0; i < 5; i++) {
        e = av_dict_get(ic->metadata, tags[i][0], NULL, 0);
        if (e)
            ui_info_put(&n, tags[i][1], e->value);
    }
    if (ic->iformat && ic->iformat->long_name)
        ui_info_put(&n, "Format", ic->iformat->long_name);
    if (ic->duration > 0) {
        s = ic->duration / AV_TIME_BASE;
        if (s >= 3600)
            snprintf(v, sizeof(v), "%d:%02d:%02d", (int)(s / 3600), (int)(s / 60 % 60), (int)(s % 60));
        else
            snprintf(v, sizeof(v), "%d:%02d", (int)(s / 60), (int)(s % 60));
        ui_info_put(&n, "Duration", v);
    }
    if (ic->bit_rate > 0) {
        snprintf(v, sizeof(v), "%d kb/s", (int)(ic->bit_rate / 1000));
        ui_info_put(&n, "Bit rate", v);
    }
    if (is->video_st && is->video_st->codecpar) {
        par = is->video_st->codecpar;
        ui_info_codec(v, sizeof(v), par->codec_id, par->profile);
        ui_info_put(&n, "Video", v);
        if (par->width > 0 && par->height > 0) {
            snprintf(v, sizeof(v), "%dx%d", par->width, par->height);
            ui_info_put(&n, "Resolution", v);
        }
        fr = av_guess_frame_rate(ic, is->video_st, NULL);
        if (fr.num > 0 && fr.den > 0) {
            snprintf(v, sizeof(v), "%.3g fps", av_q2d(fr));
            ui_info_put(&n, "Frame rate", v);
        }
        pf = par->format >= 0 ? av_get_pix_fmt_name((enum AVPixelFormat)par->format) : NULL;
        if (pf)
            ui_info_put(&n, "Pixel format", pf);
        if (par->bit_rate > 0) {
            snprintf(v, sizeof(v), "%d kb/s", (int)(par->bit_rate / 1000));
            ui_info_put(&n, "Video rate", v);
        }
    }
    if (is->audio_st && is->audio_st->codecpar) {
        par = is->audio_st->codecpar;
        ui_info_codec(v, sizeof(v), par->codec_id, par->profile);
        ui_info_put(&n, "Audio", v);
        if (par->sample_rate > 0) {
            snprintf(v, sizeof(v), "%d Hz", par->sample_rate);
            ui_info_put(&n, "Sample rate", v);
        }
        if (par->ch_layout.nb_channels > 0) {
            if (av_channel_layout_describe(&par->ch_layout, v, sizeof(v)) < 0)
                snprintf(v, sizeof(v), "%d", par->ch_layout.nb_channels);
            ui_info_put(&n, "Channels", v);
        }
        if (par->bit_rate > 0) {
            snprintf(v, sizeof(v), "%d kb/s", (int)(par->bit_rate / 1000));
            ui_info_put(&n, "Audio rate", v);
        }
    }
    return n;
}

static SDL_Rect ui_info_rect(int ww, int wh, int lines)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;
    int rows = av_clip(lines, 1, FFMAX((wh - 16 - 2 * UI_I_PAD) / UI_I_ROW, 1));

    p.w = FFMIN(FFMIN(480, FFMAX(ww / 3, 380)), ww - 16);
    p.h = 2 * UI_I_PAD + rows * UI_I_ROW;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;
    else
        p.x = FFMAX(m.x - gap - p.w, 8);
    p.y = av_clip(m.y + UI_ROW_INFO * UI_MENU_ROW - UI_I_PAD, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

static void ui_info_draw(int ww, int wh)
{
    int n = ui_info_collect(ui_menu_stream);
    SDL_Rect p = ui_info_rect(ww, wh, n);
    char val[220];
    int rows = (p.h - 2 * UI_I_PAD) / UI_I_ROW, i, cy;

    ui_glass(&p, 22);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (n == 0) {
        ui_label(p.x + 20, p.y + UI_I_PAD + UI_I_ROW / 2,
                 ui_menu_stream ? "No information in this file" : "Nothing is playing",
                 18, 220, 220, 220, 160);
        return;
    }
    for (i = 0; i < n && i < rows; i++) {
        cy = p.y + UI_I_PAD + i * UI_I_ROW + UI_I_ROW / 2;
        ui_label(p.x + 20, cy, ui_il_label[i], 16, 190, 190, 190, 200);
        av_strlcpy(val, ui_il_value[i], sizeof(val));
        ui_fit_text(val, 18, p.w - 20 - 112 - 20);
        ui_label(p.x + 20 + 112, cy, val, 18, 240, 240, 240, 255);
    }
}

/* End the file that is playing. The main loop then goes on with whatever queue_next() says. */
static void ui_end_current(VideoState *is)
{
    SDL_Event e;

    if (!is)
        return;
    ui_user_skip = 1;
    SDL_zero(e);
    e.type = FF_QUIT_EVENT;
    e.user.data1 = is;
    SDL_PushEvent(&e);
}

/* ----- "Open": the File and Folder choices ----- */
static SDL_Rect ui_open_rect(int ww, int wh)
{
    SDL_Rect m = ui_menu_rect(ww, wh), p;
    int gap = ui_idle ? 14 : 22;

    p.w = FFMAX(ui_text_width("Folder...", 22), ui_text_width("File...", 22)) + 64;
    p.h = 2 * UI_MENU_ROW + 16;
    if (m.x + m.w + gap + p.w <= ww - 8)
        p.x = m.x + m.w + gap;
    else
        p.x = FFMAX(m.x - gap - p.w, 8);
    p.y = av_clip(m.y + UI_ROW_OPEN * UI_MENU_ROW - 8, 8, FFMAX(wh - p.h - 8, 8));
    return p;
}

/* 0 = File, 1 = Folder, -1 = neither */
static int ui_open_hit(const SDL_Rect *p, int x, int y)
{
    if (x < p->x || x >= p->x + p->w || y < p->y + 8 || y >= p->y + 8 + 2 * UI_MENU_ROW)
        return -1;
    return (y - p->y - 8) / UI_MENU_ROW;
}

static void ui_open_draw(int ww, int wh)
{
    SDL_Rect p = ui_open_rect(ww, wh);
    int i, row_y;

    ui_glass(&p, 20);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < 2; i++) {
        row_y = p.y + 8 + i * UI_MENU_ROW;
        ui_label(p.x + 28, row_y + UI_MENU_ROW / 2, i ? "Folder..." : "File...", 22, 240, 240, 240,
                 i == ui_open_hover ? 255 : 205);
        if (i == ui_open_hover) {
            SDL_Rect dot = { p.x + 11, row_y + UI_MENU_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
    }
}

/* ----- the menu of a queue item (right-click) ----- */
#define UI_CTX_ROW 40

static const char *ui_ctx_label(int i)
{
    if (i == 0)
        return "Remove from queue";
    return ui_ctx_name && ui_ctx_name == q_sleep_item ? "Cancel sleep after item" : "Sleep after this item";
}

static SDL_Rect ui_ctx_rect(int ww, int wh)
{
    SDL_Rect r;
    int w = FFMAX(ui_text_width("Remove from queue", 20), ui_text_width("Cancel sleep after item", 20));

    r.w = w + 56;
    r.h = 2 * UI_CTX_ROW + 16;
    r.x = av_clip(ui_ctx_x, 8, FFMAX(ww - r.w - 8, 8));
    r.y = av_clip(ui_ctx_y, 8, FFMAX(wh - r.h - 8, 8));
    return r;
}

static int ui_ctx_hit(const SDL_Rect *r, int x, int y)
{
    if (x < r->x || x >= r->x + r->w || y < r->y + 8 || y >= r->y + 8 + 2 * UI_CTX_ROW)
        return -1;
    return (y - r->y - 8) / UI_CTX_ROW;
}

static void ui_ctx_draw(int ww, int wh)
{
    SDL_Rect r = ui_ctx_rect(ww, wh);
    int i, row_y;

    ui_glass(&r, 18);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    for (i = 0; i < 2; i++) {
        row_y = r.y + 8 + i * UI_CTX_ROW;
        ui_label(r.x + 28, row_y + UI_CTX_ROW / 2, ui_ctx_label(i), 20, 240, 240, 240,
                 i == ui_ctx_hover ? 255 : 205);
        if (i == ui_ctx_hover) {
            SDL_Rect dot = { r.x + 11, row_y + UI_CTX_ROW / 2 - 3, 6, 6 };

            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), 235);
            ui_pill(&dot);
        }
    }
}

/* 0 = remove the item, 1 = sleep after it (or stop doing that) */
static void ui_ctx_action(VideoState *is, int act)
{
    char *name = ui_ctx_name;
    int i, idx = -1, was_playing;

    ui_ctx_open = 0;
    ui_ctx_name = NULL;
    ui_ctx_hover = -1;
    for (i = 0; i < q_count; i++)
        if (q_items[i] == name)
            idx = i;
    if (idx < 0)
        return;
    if (act == 0) {
        was_playing = (idx == q_pos);
        queue_remove(idx);
        ui_q_hover_kind = UI_Q_NONE;
        ui_q_hover_idx = -1;
        if (was_playing)
            ui_end_current(is);     /* the next item takes its place */
    } else {
        q_sleep_end = 0;
        ui_sleep_gain = 1.0f;
        q_sleep_item = (q_sleep_item == q_items[idx]) ? NULL : q_items[idx];
        ui_sleep_sel = q_sleep_item ? 1 : 0;
    }
}

static void ui_q_show(void)
{
    if (!ui_q_open) {
        ui_q_reveal = 1;            /* scroll to the playing item the first time it is drawn */
        ui_q_anim_t0 = av_gettime_relative();       /* and the rows fade in */
    }
    ui_q_open = 1;
}

static void ui_menu_draw(void)
{
    SDL_Rect r, card, row, dot;
    static int was_shown = 0;
    int ww, wh, i, pad, cy, lit, shown = ui_menu_open && !ui_idle;
    double k;

    if (shown && !was_shown)
        ui_menu_anim_t0 = av_gettime_relative();     /* the rows fade in from this moment */
    was_shown = shown;
    if (ui_prefs_open || (!ui_idle && !ui_menu_open))
        return;
    if (ui_ctx_open && (!ui_q_open || (!ui_idle && !ui_menu_open)))
        ui_ctx_open = 0;
    SDL_GetWindowSize(window, &ww, &wh);
    r = ui_menu_rect(ww, wh);

    /* The popup gets a glass card around its rows. The idle screen has no card at all. */
    if (!ui_idle) {
        pad = 8;
        card.x = r.x - pad;
        card.y = r.y - pad;
        card.w = r.w + 2 * pad;
        card.h = r.h + 2 * pad;
        ui_glass(&card, 20);
    }

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    ui_ink_dark = !ui_idle;                     /* the card is light glass: dark text on it (the idle screen has no card) */
    for (i = 0; i < UI_MENU_ITEMS; i++) {
        row.x = r.x;
        row.y = r.y + i * UI_MENU_ROW;
        row.w = r.w;
        row.h = UI_MENU_ROW;
        cy = row.y + row.h / 2;
        lit = i == ui_menu_hover || (i == UI_ROW_OPEN && ui_open_open) ||
              (i == UI_ROW_QUEUE && ui_q_open) || (i == UI_ROW_INFO && ui_info_open);
        k = ui_idle ? 1.0 : av_clipd((av_gettime_relative() - ui_menu_anim_t0 - i * 40000) / 180000.0, 0.0, 1.0);
        k = 1.0 - (1.0 - k) * (1.0 - k) * (1.0 - k);        /* ease out: quick, then settling */
        ui_label(row.x + 28 + (int)((1.0 - k) * 10), cy, ui_menu_label[i], 22, 240, 240, 240,
                 (int)((lit ? 255 : 205) * k));
        if (i == UI_ROW_OPEN || i == UI_ROW_QUEUE || i == UI_ROW_INFO)
            ui_chevron(row.x + r.w - 22, cy, (int)((lit ? 255 : 170) * k));
        if (lit) {                  /* a small dot marks the row under the mouse */
            dot.x = row.x + 11;
            dot.y = cy - 3;
            dot.w = 6;
            dot.h = 6;
            SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                                   av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * k));
            ui_pill(&dot);
        }
    }
    if (ui_idle) {
        int ls, gap;

        ui_logo_metrics(ww, wh, &ls, &gap);
        ui_logo_draw(r.x - gap - ls / 2, wh / 2, ls);
    }
    ui_ink_dark = 1;                            /* the side panels are light glass too */
    if (ui_open_open)
        ui_open_draw(ww, wh);
    else if (ui_q_open)
        ui_q_draw(ww, wh);
    else if (ui_info_open)
        ui_info_draw(ww, wh);
    if (ui_ctx_open)
        ui_ctx_draw(ww, wh);
    ui_ink_dark = 0;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Do what a menu row says */
static void ui_menu_action(VideoState *is, int item)
{
    if (item == UI_ROW_OPEN) {          /* Open: the choices appear beside it */
        ui_open_open = 1;
        ui_q_open = 0;
        ui_info_open = 0;
        return;
    }
    if (item == UI_ROW_QUEUE) {         /* Queue: show the queue panel */
        ui_q_show();
        ui_info_open = 0;
        ui_open_open = 0;
        return;
    }
    if (item == UI_ROW_INFO) {          /* Media Info: show the information panel */
        ui_info_open = 1;
        ui_q_open = 0;
        ui_open_open = 0;
        return;
    }
    ui_menu_open = 0;
    ui_menu_hover = -1;
    ui_q_open = 0;
    ui_info_open = 0;
    ui_open_open = 0;
    if (item == UI_ROW_PREFS) {
        ui_prefs_open = 1;
        ui_prefs_hover = -1;
    } else {
        do_exit(is);                /* Quit */
    }
}

/* Mouse events in the queue panel. Returns 1 if the panel used the event. */
static int ui_q_mouse(VideoState *is, SDL_Event *ev, int ww, int wh, int x, int y)
{
    SDL_Rect p = ui_q_rect(ww, wh);
    int item, kind = ui_q_hit(&p, wh, x, y, &item);
    int was_playing;

    if (ev->type == SDL_MOUSEMOTION) {
        ui_q_hover_kind = kind;
        ui_q_hover_idx = item;
        if (kind != UI_Q_NONE) {
            ui_menu_hover = UI_ROW_QUEUE;   /* the "Queue" row stays lit while the mouse is in the panel */
            return 1;
        }
        return 0;
    }
    if (ev->type != SDL_MOUSEBUTTONDOWN || ev->button.button != SDL_BUTTON_LEFT)
        return 0;
    if (kind == UI_Q_NONE)          /* a click on the panel's padding does nothing */
        return x >= p.x && x < p.x + p.w && y >= p.y && y < p.y + p.h;

    if (kind == UI_Q_ADD) {
        ui_menu_open = 0;
        ui_q_open = 0;
        ui_menu_hover = -1;
        ui_pick_start(2);           /* choose files to add to the queue */
    } else if (kind == UI_Q_SHUF) {
        queue_set_shuffle(!q_shuffle);
    } else if (kind == UI_Q_PREV) {
        q_step = -1;                /* the main loop plays the item before this one */
        ui_end_current(is);
    } else if (kind == UI_Q_NEXT) {
        q_step = 1;
        ui_end_current(is);
    } else if (kind == UI_Q_PLAY) {
        if (is)
            toggle_pause(is);
        else if (q_count > 0)       /* the idle screen: play the queue from the top, or go on after a sleep stop */
            q_forced = (q_hold && q_pos + 1 < q_count) ? q_pos + 1 : 0;
    } else if (kind == UI_Q_XF_DEC || kind == UI_Q_XF_INC) {
        cfg_crossfade = av_clip(cfg_crossfade + (kind == UI_Q_XF_INC ? 1 : -1), 0, 10);
        settings_save();
    } else if (kind == UI_Q_XFCHIP) {
        cfg_crossfade = ui_xf_vals[av_clip(item, 0, 6)];
        settings_save();
    } else if (kind == UI_Q_XFROW) {
        /* the row itself: the choices are showing, nothing to do */
    } else if (kind == UI_Q_CHIP) {
        ui_sleep_choose(item);
    } else if (kind == UI_Q_SLEEP) {
        /* the row itself: the choices are showing, nothing to do */
    } else if (kind == UI_Q_DEL) {
        was_playing = (item == q_pos);
        queue_remove(item);
        ui_q_hover_kind = UI_Q_NONE;
        ui_q_hover_idx = -1;
        if (was_playing)
            ui_end_current(is);     /* the next item takes its place */
    } else if (kind == UI_Q_DOT) {
        ui_q_drag = item;           /* start dragging this item */
        ui_q_drag_y = y;
        SDL_CaptureMouse(SDL_TRUE); /* keep getting the mouse even outside the window */
    } else {                        /* an item: play it now */
        q_forced = item;
        ui_end_current(is);         /* the menu stays open, so you can keep browsing the queue */
    }
    return 1;
}

/* Mouse events for the menu. Returns 1 if the menu used the event.
   is = the stream playing now, or NULL on the idle screen. */
static int ui_menu_mouse(VideoState *is, SDL_Event *ev)
{
    SDL_Rect r, p, ip, op;
    int ww, wh, x, y, row, kind, item, hit;

    if (ui_prefs_open)
        return ui_prefs_mouse(is, ev);

    ui_menu_last_move = av_gettime_relative();     /* the popup closes when the mouse rests */

    if (ui_ctx_open && (!ui_q_open || (!ui_idle && !ui_menu_open)))
        ui_ctx_open = 0;
    if (ui_ctx_open) {              /* the item menu owns the mouse until it closes */
        SDL_GetWindowSize(window, &ww, &wh);
        op = ui_ctx_rect(ww, wh);
        x = (ev->type == SDL_MOUSEMOTION) ? ev->motion.x : ev->button.x;
        y = (ev->type == SDL_MOUSEMOTION) ? ev->motion.y : ev->button.y;
        hit = ui_ctx_hit(&op, x, y);
        if (ev->type == SDL_MOUSEMOTION) {
            ui_ctx_hover = hit;
        } else if (ev->type == SDL_MOUSEBUTTONDOWN) {
            if (ev->button.button == SDL_BUTTON_LEFT && hit >= 0)
                ui_ctx_action(is, hit);
            else
                ui_ctx_open = 0;    /* a click anywhere else (or a right-click) closes it */
        }
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;
    }

    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && ui_q_open &&
        ui_q_drag < 0 && (ui_idle || ui_menu_open)) {
        /* right-click on a queue item: its own menu */
        SDL_GetWindowSize(window, &ww, &wh);
        p = ui_q_rect(ww, wh);
        kind = ui_q_hit(&p, wh, ev->button.x, ev->button.y, &item);
        if (item >= 0 && (kind == UI_Q_ITEM || kind == UI_Q_DOT || kind == UI_Q_DEL)) {
            ui_ctx_open = 1;
            ui_ctx_x = ev->button.x;
            ui_ctx_y = ev->button.y;
            ui_ctx_name = q_items[item];
            ui_ctx_hover = -1;
            ui_wake();
            if (is)
                is->force_refresh = 1;
            return 1;
        }
        if (ev->button.x >= p.x && ev->button.x < p.x + p.w && ev->button.y >= p.y && ev->button.y < p.y + p.h)
            return 1;               /* a right-click on the rest of the panel does nothing */
    }
    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_RIGHT && !ui_idle) {
        /* right-click on the video: open the menu at the mouse */
        ui_menu_open = 1;
        ui_menu_x = ev->button.x;
        ui_menu_y = ev->button.y;
        ui_menu_hover = -1;
        ui_q_open = 0;
        ui_info_open = 0;
        ui_open_open = 0;
        ui_q_drag = -1;
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (!ui_idle && !ui_menu_open)
        return 0;

    SDL_GetWindowSize(window, &ww, &wh);
    r = ui_menu_rect(ww, wh);
    x = (ev->type == SDL_MOUSEMOTION) ? ev->motion.x : ev->button.x;
    y = (ev->type == SDL_MOUSEMOTION) ? ev->motion.y : ev->button.y;
    row = (x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h) ? (y - r.y) / UI_MENU_ROW : -1;

    if (ui_q_drag >= 0) {           /* dragging a queue item: the panel owns the mouse */
        if (ev->type == SDL_MOUSEMOTION) {
            ui_q_drag_y = y;
            ui_wake();
            ui_q_autoscroll();
        }
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (ui_open_open) {             /* the File / Folder choices */
        op = ui_open_rect(ww, wh);
        hit = ui_open_hit(&op, x, y);
        if (hit >= 0 || (x >= op.x && x < op.x + op.w && y >= op.y && y < op.y + op.h)) {
            if (ev->type == SDL_MOUSEMOTION) {
                ui_open_hover = hit;
                ui_menu_hover = UI_ROW_OPEN;    /* the "Open" row stays lit */
            } else if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_LEFT && hit >= 0) {
                ui_menu_open = 0;
                ui_menu_hover = -1;
                ui_open_open = 0;
                ui_open_hover = -1;
                ui_pick_start(hit);     /* 0 = Open File, 1 = Open Folder */
            }
            ui_wake();
            if (is)
                is->force_refresh = 1;
            return 1;
        }
        ui_open_hover = -1;
    }
    if (ui_q_open && ui_q_mouse(is, ev, ww, wh, x, y)) {
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    if (ui_info_open) {             /* the information panel only shows things, but it keeps the mouse */
        ip = ui_info_rect(ww, wh, ui_info_collect(is));
        if (x >= ip.x && x < ip.x + ip.w && y >= ip.y && y < ip.y + ip.h) {
            if (ev->type == SDL_MOUSEMOTION)
                ui_menu_hover = UI_ROW_INFO;
            if (is)
                is->force_refresh = 1;
            return 1;
        }
    }

    if (ev->type == SDL_MOUSEMOTION) {
        ui_menu_hover = row;
        if (row == UI_ROW_OPEN) {
            ui_open_open = 1;       /* hovering "Open" shows File... and Folder... */
            ui_q_open = 0;
            ui_info_open = 0;
        } else if (row == UI_ROW_QUEUE) {
            ui_q_show();            /* hovering "Queue" opens the queue panel */
            ui_info_open = 0;
            ui_open_open = 0;
        } else if (row == UI_ROW_INFO) {
            ui_info_open = 1;       /* hovering "Media Info" opens the information panel */
            ui_q_open = 0;
            ui_open_open = 0;
        } else {
            if (ui_open_open) {
                op = ui_open_rect(ww, wh);
                if (!ui_q_keep(&r, &op, x, y, UI_ROW_OPEN))
                    ui_open_open = 0;
            }
            if (ui_q_open) {
                p = ui_q_rect(ww, wh);
                if (!ui_q_keep(&r, &p, x, y, UI_ROW_QUEUE))
                    ui_q_open = 0;
            }
            if (ui_info_open) {
                ip = ui_info_rect(ww, wh, ui_info_collect(is));
                if (!ui_q_keep(&r, &ip, x, y, UI_ROW_INFO))
                    ui_info_open = 0;
            }
        }
        ui_wake();
        if (is)
            is->force_refresh = 1;
        return ui_menu_open;        /* the popup swallows mouse movement; the idle screen doesn't */
    }
    if (ev->type == SDL_MOUSEBUTTONDOWN && ev->button.button == SDL_BUTTON_LEFT) {
        if (row >= 0) {
            ui_menu_action(is, row);
        } else if (ui_menu_open) {
            ui_menu_open = 0;       /* click outside closes the popup */
            ui_q_open = 0;
            ui_info_open = 0;
            ui_open_open = 0;
        } else {
            return 0;               /* idle screen: clicking elsewhere moves the window */
        }
        if (is)
            is->force_refresh = 1;
        return 1;
    }
    return 0;
}

/* The mouse button was released: drop the dragged queue item. Returns 1 if there was a drag. */
static int ui_queue_release(SDL_Event *ev)
{
    SDL_Rect p;
    int ww, wh;

    if (ui_q_drag < 0 || ev->button.button != SDL_BUTTON_LEFT)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_q_rect(ww, wh);
    ui_q_drag_y = ev->button.y;
    queue_move(ui_q_drag, ui_q_drop(wh, &p));
    ui_q_drag = -1;
    SDL_CaptureMouse(SDL_FALSE);
    return 1;
}

/* Mouse wheel: scroll the queue panel. Returns 1 if the panel used it. */
static int ui_queue_wheel(SDL_Event *ev)
{
    int ww, wh;

    if (!ui_q_open || (!ui_idle && !ui_menu_open) || ui_prefs_open || !ev->wheel.y)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    ui_q_scroll = av_clip(ui_q_scroll - ev->wheel.y, 0, FFMAX(q_count - ui_q_visible(wh), 0));
    return 1;
}

/* The popup menu closes when the mouse has rested on it for 5 seconds, unless the mouse is on the
   Open, Queue or Media Info panel (while a panel is open, it keeps the menu open). While the queue panel
   is showing, the picture is redrawn every second so the counter keeps up. */
static void ui_menu_tick(VideoState *is)
{
    static int64_t last_second = 0;
    static int seen_gen = -1;
    int64_t second = av_gettime_relative() / 1000000;

    if (ui_menu_open && !ui_idle && av_gettime_relative() - ui_menu_anim_t0 < 600000)
        is->force_refresh = 1;                  /* the rows are still fading in */
    if (ui_flow_wants_redraw(is))
        is->force_refresh = 1;                  /* the disc turns, the bars move, the covers glide */
    if (ui_q_open && ui_q_off != 0.0)
        is->force_refresh = 1;                  /* the queue list is still gliding */
    if ((ui_q_open && (ui_chip_anim || ui_xf_anim)) || (ui_prefs_open && ui_prefs_anim))
        is->force_refresh = 1;                  /* a row is changing into its choices, or back */
    if (ui_q_open && av_gettime_relative() - ui_q_anim_t0 < 700000)
        is->force_refresh = 1;                  /* the queue rows are still fading in */
    if (ui_q_open && (ui_menu_open || ui_idle) && (second != last_second || seen_gen != q_dur_gen)) {
        last_second = second;
        seen_gen = q_dur_gen;
        is->force_refresh = 1;
    }
    if (!ui_menu_open || ui_idle || ui_prefs_open || ui_q_drag >= 0 || ui_q_open || ui_info_open ||
        ui_open_open || ui_ctx_open)
        return;
    if (av_gettime_relative() - ui_menu_last_move > 5000000) {
        ui_menu_open = 0;
        ui_menu_hover = -1;
        is->force_refresh = 1;
    }
}

/* While an item is dragged near the top or bottom of the queue list, the list scrolls so the item can
   go anywhere in a long queue. The further out the mouse is, the faster it scrolls.
   Returns 1 if the list scrolled. */
static int ui_q_autoscroll(void)
{
    SDL_Rect p;
    int ww, wh, top, bottom, vis, step = 0, before;
    int64_t now = av_gettime_relative();

    if (ui_q_drag < 0 || now < ui_q_scroll_next)
        return 0;
    SDL_GetWindowSize(window, &ww, &wh);
    p = ui_q_rect(ww, wh);
    vis = ui_q_visible(wh);
    top = p.y + UI_Q_PAD + UI_Q_HEAD + UI_Q_ROW / 2;
    bottom = p.y + UI_Q_PAD + UI_Q_HEAD + vis * UI_Q_ROW - UI_Q_ROW / 2;
    if (ui_q_drag_y < top)
        step = -(1 + (top - ui_q_drag_y) / UI_Q_ROW);
    else if (ui_q_drag_y > bottom)
        step = 1 + (ui_q_drag_y - bottom) / UI_Q_ROW;
    if (!step)
        return 0;
    before = ui_q_scroll;
    ui_q_scroll = av_clip(ui_q_scroll + step, 0, FFMAX(q_count - vis, 0));
    ui_q_scroll_next = now + 90000;             /* about 11 rows a second at the edge */
    return ui_q_scroll != before;
}

/* The screen may go to sleep unless a video is actually playing: while paused, on the idle
   screen, or while only music plays, the system's sleep and screen-off settings apply again. */
static void ui_power_tick(VideoState *is)
{
    static int inhibit = -1;
    static int64_t asserted = 0;
    int64_t now = av_gettime_relative();
    int want = is && !is->paused && !is->ui_held && is->video_st &&
               !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);

    if (want == inhibit && now - asserted < 2000000)    /* checked again every 2 s, not only when the state changes */
        return;
    if (want != inhibit)
        av_log(NULL, AV_LOG_INFO, want ? "screen kept awake (a video is playing)\n"
                                       : "screen may sleep (the system's idle settings apply)\n");
    inhibit = want;
    asserted = now;
    if (want)
        SDL_DisableScreenSaver();       /* playing a video: keep the screen on */
    else
        SDL_EnableScreenSaver();
}

/* ---- keyboard shortcuts that can be changed in settings.conf ---- */
enum { UK_PAUSE, UK_FULLSCREEN, UK_MUTE, UK_NEXT, UK_PREVIOUS, UK_SEEK_BACK, UK_SEEK_FORWARD,
       UK_VOL_UP, UK_VOL_DOWN, UK_QUIT, UK_COUNT };

static const struct { const char *name; SDL_Keycode def; } ui_key_def[UK_COUNT] = {
    { "pause", SDLK_SPACE }, { "fullscreen", SDLK_f }, { "mute", SDLK_m }, { "next", SDLK_n },
    { "previous", SDLK_p }, { "seek_back", SDLK_LEFT }, { "seek_forward", SDLK_RIGHT },
    { "volume_up", SDLK_UP }, { "volume_down", SDLK_DOWN }, { "quit", SDLK_q }
};
static SDL_Keycode ui_key_cur[UK_COUNT];    /* the key each action uses now */
static int ui_key_ready = 0;

static void ui_key_init(void)
{
    int i;

    if (ui_key_ready)
        return;
    for (i = 0; i < UK_COUNT; i++)
        ui_key_cur[i] = ui_key_def[i].def;
    ui_key_ready = 1;
}

/* A key you chose acts as the standard key of its action, and the standard key of an action you
   moved elsewhere does nothing any more. Everything else is left alone. */
static SDL_Keycode ui_key_translate(SDL_Keycode k)
{
    int i;

    ui_key_init();
    for (i = 0; i < UK_COUNT; i++)
        if (ui_key_cur[i] != ui_key_def[i].def && k == ui_key_cur[i])
            return ui_key_def[i].def;
    for (i = 0; i < UK_COUNT; i++)
        if (ui_key_cur[i] != ui_key_def[i].def && k == ui_key_def[i].def)
            return SDLK_UNKNOWN;
    return k;
}

/* A line like "key_fullscreen = g" of settings.conf. Returns 1 if it was a key line. */
static int ui_key_parse_line(const char *line)
{
    char name[40], val[64];
    SDL_Keycode k;
    size_t n;
    int i;

    if (sscanf(line, " key_%39[a-z_] = %63[^\n]", name, val) != 2)
        return 0;
    n = strlen(val);
    while (n > 0 && (val[n - 1] == ' ' || val[n - 1] == '\r' || val[n - 1] == '\t'))
        val[--n] = 0;
    k = SDL_GetKeyFromName(val);
    ui_key_init();
    for (i = 0; i < UK_COUNT; i++)
        if (!strcmp(name, ui_key_def[i].name)) {
            if (k != SDLK_UNKNOWN)
                ui_key_cur[i] = k;
            break;
        }
    return 1;
}

/* Write the key bindings into settings.conf (lines at their standard key start with a #) */
static void ui_key_save(FILE *f)
{
    int i;

    ui_key_init();
    fprintf(f, "# Keyboard shortcuts. Remove the # in front of a line and choose another key.\n");
    fprintf(f, "# Key names: letters and digits, F1 to F12, Space, Return, Tab, Left, Right, Up, Down,\n");
    fprintf(f, "# Page Up, Page Down, Home, End ... A key moved to another action stops doing what it did.\n");
    for (i = 0; i < UK_COUNT; i++)
        fprintf(f, "%skey_%s = %s\n", ui_key_cur[i] == ui_key_def[i].def ? "# " : "",
                ui_key_def[i].name, SDL_GetKeyName(ui_key_cur[i]));
    fprintf(f, "\n");
}

/* Read the key bindings. The first time after an update the file has none, so they are written
   into it, to be found and changed. */
static void ui_key_load(void)
{
    char path[1024], line[256];
    const char *home = getenv("HOME");
    FILE *f;
    int seen = 0;

    ui_key_init();
    if (!home)
        return;
    snprintf(path, sizeof(path), "%s/.config/ffplay-custom/settings.conf", home);
    f = fopen(path, "r");
    if (!f)
        return;
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, "key_pause"))
            seen = 1;
        ui_key_parse_line(line);
    }
    fclose(f);
    if (!seen)
        settings_save();
}

/* display the current picture, if any */
/* ----- the cover-flow queue: shown while audio plays -----
   Every item in the queue is a cover. The one playing is large in the middle with a spinning disc behind it; the
   others sit on both sides, smaller. Pictures are read in the background: the picture attached to an audio file,
   or a frame from near the start of a video. */
typedef struct UiCov {
    char *path;
    int state;                  /* 0 = being read, 1 = pixels ready, 2 = texture ready, 3 = no picture */
    uint8_t *px;
    int w, h;                   /* the size of the texture */
    int cw, ch;                 /* the size of the picture inside it (smaller on one side if it was a video frame) */
    int tr, tg, tb;             /* the average color of the picture, for the disc */
    SDL_Texture *tex;
    uint8_t *npx;               /* a video frame in its own shape (rounded corners), for the video tiles */
    int nw, nh;
    SDL_Texture *ntex;
} UiCov;

static UiCov *ui_cov = NULL;
static int ui_cov_n = 0, ui_cov_cap = 0;
static SDL_mutex *ui_cov_mu = NULL;
static SDL_cond *ui_cov_cv = NULL;
static int ui_cov_todo[1024];
static unsigned ui_cov_head = 0, ui_cov_tail = 0;

/* Read a picture for a file: RGBA pixels, at most 256 on the long side. NULL if there is none. */
static uint8_t *ui_cov_decode(const char *path, int *ow, int *oh, int *cw, int *ch, uint8_t **nat, int *nw, int *nh)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    AVFrame *fr = NULL;
    AVPacket *pk = NULL;
    struct SwsContext *sws = NULL;
    const AVCodec *codec;
    AVStream *st = NULL;
    uint8_t *out = NULL, *dst[4] = { NULL };
    int ls[4] = { 0 }, i, n, w, h, got = 0;
    uint8_t *sq = NULL, *tiny = NULL, *tdst[4] = { NULL };
    struct SwsContext *sws2 = NULL;
    int tls[4] = { 0 }, x, y, ox, oy;
    uint8_t *nt = NULL;

    *nat = NULL;
    *nw = *nh = 0;
    if (strstr(path, "://"))
        return NULL;
    if (avformat_open_input(&ic, path, NULL, NULL) < 0)
        return NULL;
    avformat_find_stream_info(ic, NULL);
    for (i = 0; i < (int)ic->nb_streams; i++)
        if (ic->streams[i]->disposition & AV_DISPOSITION_ATTACHED_PIC) {
            st = ic->streams[i];
            break;
        }
    for (i = 0; !st && i < (int)ic->nb_streams; i++)
        if (ic->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO)
            st = ic->streams[i];
    if (!st)
        goto end;
    codec = avcodec_find_decoder(st->codecpar->codec_id);
    cc = codec ? avcodec_alloc_context3(codec) : NULL;
    if (!cc || avcodec_parameters_to_context(cc, st->codecpar) < 0 || avcodec_open2(cc, codec, NULL) < 0)
        goto end;
    fr = av_frame_alloc();
    pk = av_packet_alloc();
    if (!fr || !pk)
        goto end;
    if (st->disposition & AV_DISPOSITION_ATTACHED_PIC) {
        if (avcodec_send_packet(cc, &st->attached_pic) >= 0) {
            avcodec_send_packet(cc, NULL);
            got = avcodec_receive_frame(cc, fr) >= 0;
        }
    } else {
        if (ic->duration > 0)
            av_seek_frame(ic, -1, ic->duration / 10, AVSEEK_FLAG_BACKWARD);     /* a frame a tenth of the way in */
        for (n = 0; !got && n < 400 && av_read_frame(ic, pk) >= 0; n++) {
            if (pk->stream_index == st->index && avcodec_send_packet(cc, pk) >= 0)
                got = avcodec_receive_frame(cc, fr) >= 0;
            av_packet_unref(pk);
        }
    }
    if (!got || fr->width <= 0 || fr->height <= 0)
        goto end;
    if (fr->width >= fr->height) {
        w = 256;
        h = FFMAX(fr->height * 256 / fr->width, 1);
    } else {
        h = 256;
        w = FFMAX(fr->width * 256 / fr->height, 1);
    }
    sws = sws_getContext(fr->width, fr->height, fr->format, w, h, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
    out = av_malloc((size_t)w * h * 4);
    if (!sws || !out) {
        av_freep(&out);
        goto end;
    }
    dst[0] = out;
    ls[0] = w * 4;
    sws_scale(sws, (const uint8_t *const *)fr->data, fr->linesize, 0, fr->height, dst, ls);
    *ow = w;
    *oh = h;
    *cw = w;
    *ch = h;
    if (w != h && w >= 32 && h >= 32 && !(st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
        /* a video frame: keep a copy in its own shape, with rounded corners, for the video tiles */
        int rr = FFMIN(w, h) / 11, k;

        nt = av_malloc((size_t)w * h * 4);
        if (nt) {
            memcpy(nt, out, (size_t)w * h * 4);
            for (y = 0; y < rr; y++)
                for (x = 0; x < rr; x++) {
                    double dxx = rr - x - 0.5, dyy = rr - y - 0.5;
                    double cov = av_clipd(rr - sqrt(dxx * dxx + dyy * dyy) + 0.5, 0.0, 1.0);
                    int at[4] = { y * w + x, y * w + w - 1 - x, (h - 1 - y) * w + x, (h - 1 - y) * w + w - 1 - x };

                    for (k = 0; k < 4; k++)
                        nt[at[k] * 4 + 3] = (uint8_t)(nt[at[k] * 4 + 3] * cov);
                }
        }
    }
    if (w != h) {       /* not square (a video frame): a square with the picture in the middle and a frosted blur around it */
        sq = av_malloc(256 * 256 * 4);
        tiny = av_malloc(16 * 16 * 4);
        sws2 = sws_getContext(fr->width, fr->height, fr->format, 16, 16, AV_PIX_FMT_RGBA, SWS_AREA, NULL, NULL, NULL);
        if (!sq || !tiny || !sws2) {
            av_freep(&out);
            goto end;
        }
        tdst[0] = tiny;
        tls[0] = 16 * 4;
        sws_scale(sws2, (const uint8_t *const *)fr->data, fr->linesize, 0, fr->height, tdst, tls);
        for (y = 0; y < 256; y++)
            for (x = 0; x < 256; x++) {
                double fx = x * 15.0 / 255.0, fy = y * 15.0 / 255.0, ax, ay;
                int x0 = (int)fx, y0 = (int)fy, x1 = FFMIN(x0 + 1, 15), y1 = FFMIN(y0 + 1, 15), k;

                ax = fx - x0;
                ay = fy - y0;
                for (k = 0; k < 4; k++) {
                    double v = (tiny[(y0 * 16 + x0) * 4 + k] * (1 - ax) + tiny[(y0 * 16 + x1) * 4 + k] * ax) * (1 - ay) +
                               (tiny[(y1 * 16 + x0) * 4 + k] * (1 - ax) + tiny[(y1 * 16 + x1) * 4 + k] * ax) * ay;

                    {
                        double bc = k == 0 ? cfg_bar_r : k == 1 ? cfg_bar_g : cfg_bar_b;     /* frosted, in your bar color */

                        sq[(y * 256 + x) * 4 + k] = (uint8_t)(k < 3 ? FFMIN((v * 0.8 + 40.0) * 0.6 + bc * 0.4, 255.0) : 255.0);
                    }
                }
            }
        ox = (256 - w) / 2;
        oy = (256 - h) / 2;
        for (y = 0; y < h; y++)
            memcpy(sq + ((oy + y) * 256 + ox) * 4, out + (size_t)y * w * 4, w * 4);
        av_freep(&out);
        out = sq;
        sq = NULL;
        *ow = 256;
        *oh = 256;
    }
    if (*ow == *oh && *ow >= 64) {      /* round the corners: the transparent corners are baked into the picture */
        int sz = *ow, rr = *ow / 11, k;

        for (y = 0; y < rr; y++)
            for (x = 0; x < rr; x++) {
                double dxx = rr - x - 0.5, dyy = rr - y - 0.5;
                double cov = av_clipd(rr - sqrt(dxx * dxx + dyy * dyy) + 0.5, 0.0, 1.0);
                int at[4] = { y * sz + x, y * sz + sz - 1 - x, (sz - 1 - y) * sz + x, (sz - 1 - y) * sz + sz - 1 - x };

                for (k = 0; k < 4; k++)
                    out[at[k] * 4 + 3] = (uint8_t)(out[at[k] * 4 + 3] * cov);
            }
    }
end:
    if (out && nt) {
        *nat = nt;
        *nw = w;
        *nh = h;
    } else {
        av_free(nt);
    }
    sws_freeContext(sws);
    sws_freeContext(sws2);
    av_free(tiny);
    av_free(sq);
    av_frame_free(&fr);
    av_packet_free(&pk);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    return out;
}

static int ui_cov_thread(void *arg)
{
    char *p;
    uint8_t *px, *npx = NULL;
    int k, w, h, cw, ch, nw = 0, nh = 0;

    for (;;) {
        SDL_LockMutex(ui_cov_mu);
        while (ui_cov_head >= ui_cov_tail)
            SDL_CondWait(ui_cov_cv, ui_cov_mu);
        k = ui_cov_todo[ui_cov_head++ % 1024];
        p = av_strdup(ui_cov[k].path);
        SDL_UnlockMutex(ui_cov_mu);

        w = h = cw = ch = 0;
        npx = NULL;
        px = p ? ui_cov_decode(p, &w, &h, &cw, &ch, &npx, &nw, &nh) : NULL;
        av_free(p);

        SDL_LockMutex(ui_cov_mu);
        ui_cov[k].px = px;
        ui_cov[k].w = w;
        ui_cov[k].h = h;
        ui_cov[k].cw = cw;
        ui_cov[k].ch = ch;
        ui_cov[k].npx = npx;
        ui_cov[k].nw = nw;
        ui_cov[k].nh = nh;
        ui_cov[k].state = px ? 1 : 3;
        SDL_UnlockMutex(ui_cov_mu);
    }
    return 0;
}

/* The picture of a file as a texture, or NULL while it is still being read (or if there is none) */
static SDL_Texture *ui_cov_get(const char *path, int *w, int *h)
{
    SDL_Texture *t = NULL;
    UiCov *grown, *c;
    SDL_Thread *th;
    int i, found = -1;

    if (!path)
        return NULL;
    if (!ui_cov_mu) {
        ui_cov_mu = SDL_CreateMutex();
        ui_cov_cv = SDL_CreateCond();
        if (!ui_cov_mu || !ui_cov_cv)
            return NULL;
        th = SDL_CreateThread(ui_cov_thread, "cover", NULL);
        if (th)
            SDL_DetachThread(th);
    }
    SDL_LockMutex(ui_cov_mu);
    for (i = 0; i < ui_cov_n; i++)
        if (!strcmp(ui_cov[i].path, path)) {
            found = i;
            break;
        }
    if (found < 0 && ui_cov_n < 1000) {
        if (ui_cov_n >= ui_cov_cap) {
            grown = av_realloc_array(ui_cov, FFMAX(ui_cov_cap * 2, 64), sizeof(*ui_cov));
            if (grown) {
                ui_cov = grown;
                ui_cov_cap = FFMAX(ui_cov_cap * 2, 64);
            }
        }
        if (ui_cov_n < ui_cov_cap) {
            c = &ui_cov[ui_cov_n];
            memset(c, 0, sizeof(*c));
            c->path = av_strdup(path);
            if (c->path) {
                found = ui_cov_n++;
                ui_cov_todo[ui_cov_tail++ % 1024] = found;
                SDL_CondSignal(ui_cov_cv);
            }
        }
    }
    if (found >= 0) {
        c = &ui_cov[found];
        if (c->state == 1) {                    /* the pixels are ready: make the texture here, in the drawing thread */
            c->tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, c->w, c->h);
            if (c->tex) {
                SDL_UpdateTexture(c->tex, NULL, c->px, c->w * 4);
                SDL_SetTextureBlendMode(c->tex, SDL_BLENDMODE_BLEND);
            }
            {                                   /* the average color (the see-through corners are skipped) */
                long sr = 0, sg = 0, sb = 0, cnt = 0;
                int q;

                for (q = 0; q < c->w * c->h; q += 3) {
                    const uint8_t *p = c->px + q * 4;

                    if (p[3] > 200) {
                        sr += p[0];
                        sg += p[1];
                        sb += p[2];
                        cnt++;
                    }
                }
                c->tr = cnt ? (int)(sr / cnt) : 40;
                c->tg = cnt ? (int)(sg / cnt) : 40;
                c->tb = cnt ? (int)(sb / cnt) : 40;
            }
            av_freep(&c->px);
            if (c->npx) {                       /* the video frame in its own shape */
                c->ntex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, c->nw, c->nh);
                if (c->ntex) {
                    SDL_UpdateTexture(c->ntex, NULL, c->npx, c->nw * 4);
                    SDL_SetTextureBlendMode(c->ntex, SDL_BLENDMODE_BLEND);
                }
                av_freep(&c->npx);
            }
            c->state = c->tex ? 2 : 3;
        }
        if (c->state == 2) {
            t = c->tex;
            *w = c->cw;
            *h = c->ch;
        }
    }
    SDL_UnlockMutex(ui_cov_mu);
    return t;
}

/* The picture of a file, if it is ready, and the color for its disc: its average color, a bit richer, and not too dark
   or too light. Without a picture the color comes from your bar color. */
static SDL_Texture *ui_cov_tone(const char *path, SDL_Color *dc)
{
    SDL_Texture *t = NULL;
    double h, s, v;
    int i, r = cfg_bar_r / 2, g = cfg_bar_g / 2, b = cfg_bar_b / 2;

    dc->a = 255;
    if (path && ui_cov_mu) {
        SDL_LockMutex(ui_cov_mu);
        for (i = 0; i < ui_cov_n; i++)
            if (!strcmp(ui_cov[i].path, path)) {
                if (ui_cov[i].state == 2) {
                    t = ui_cov[i].tex;
                    r = ui_cov[i].tr;
                    g = ui_cov[i].tg;
                    b = ui_cov[i].tb;
                }
                break;
            }
        SDL_UnlockMutex(ui_cov_mu);
        if (t) {
            ui_rgb2hsv(r, g, b, &h, &s, &v);
            ui_hsv2rgb(h, FFMIN(s * 1.3, 0.85), av_clipd(v * 1.1, 0.40, 0.78), dc);
            return t;
        }
    }
    dc->r = (Uint8)r;
    dc->g = (Uint8)g;
    dc->b = (Uint8)b;
    return NULL;
}

/* A filled slice of a circle (a pie) in one color */
static void ui_fan(double cx, double cy, double r, double a0, double a1, int seg, int cr, int cg, int cb, int ca)
{
    SDL_Vertex v[50];
    int idx[48 * 3], k;
    SDL_Color c;

    seg = av_clip(seg, 1, 48);
    c.r = (Uint8)cr;
    c.g = (Uint8)cg;
    c.b = (Uint8)cb;
    c.a = (Uint8)av_clip(ca, 0, 255);
    v[0].position.x = (float)cx;
    v[0].position.y = (float)cy;
    v[0].color = c;
    v[0].tex_coord.x = 0;
    v[0].tex_coord.y = 0;
    for (k = 0; k <= seg; k++) {
        double a = a0 + (a1 - a0) * k / seg;

        v[k + 1].position.x = (float)(cx + r * cos(a));
        v[k + 1].position.y = (float)(cy + r * sin(a));
        v[k + 1].color = c;
        v[k + 1].tex_coord.x = 0;
        v[k + 1].tex_coord.y = 0;
    }
    for (k = 0; k < seg; k++) {
        idx[k * 3] = 0;
        idx[k * 3 + 1] = k + 1;
        idx[k * 3 + 2] = k + 2;
    }
    SDL_RenderGeometry(renderer, NULL, v, seg + 2, idx, seg * 3);
}

/* The spinning disc: solid, in a color from the cover, with a few grooves, light turning across it, and a big label that
   is a round piece of the cover turning with the disc (pic is NULL while the cover is not ready) */
static void ui_flow_disc(double cx, double cy, double r, double ang, int a, SDL_Texture *pic, SDL_Color base)
{
    const double two_pi = 6.28318531, pi = 3.14159265, lab = 0.74;      /* the label is nearly all of the disc */
    double k, f;
    int i;

    ui_fan(cx, cy, r, 0, two_pi, 48, base.r, base.g, base.b, a);                /* the solid disc */
    for (k = 0.95, i = 0; k > lab + 0.03; k -= 0.05, i++) {                     /* grooves in the band around the label */
        f = i % 2 ? 0.84 : 1.08;
        ui_fan(cx, cy, r * k, 0, two_pi, 48, FFMIN((int)(base.r * f), 255), FFMIN((int)(base.g * f), 255),
               FFMIN((int)(base.b * f), 255), a);
    }
    ui_fan(cx, cy, r * 0.97, ang, ang + 0.55, 8, 255, 255, 255, a * 40 / 255);  /* light turning across the grooves */
    ui_fan(cx, cy, r * 0.97, ang + pi, ang + pi + 0.55, 8, 255, 255, 255, a * 40 / 255);
    ui_fan(cx, cy, r * (lab + 0.025), 0, two_pi, 40, base.r * 6 / 10, base.g * 6 / 10, base.b * 6 / 10, a);   /* rim of the label */
    if (pic) {                                  /* the label: a piece of the cover, turning with the disc */
        SDL_Vertex v[34];
        int idx[32 * 3];
        SDL_Color w;

        w.r = 255;
        w.g = 255;
        w.b = 255;
        w.a = (Uint8)av_clip(a, 0, 255);
        SDL_SetTextureAlphaMod(pic, 255);
        SDL_SetTextureColorMod(pic, 255, 255, 255);
        v[0].position.x = (float)cx;
        v[0].position.y = (float)cy;
        v[0].color = w;
        v[0].tex_coord.x = 0.5f;
        v[0].tex_coord.y = 0.5f;
        for (i = 0; i <= 32; i++) {
            double an = i * two_pi / 32;

            v[i + 1].position.x = (float)(cx + r * lab * cos(an));
            v[i + 1].position.y = (float)(cy + r * lab * sin(an));
            v[i + 1].color = w;
            v[i + 1].tex_coord.x = (float)(0.5 + 0.34 * cos(an - ang));
            v[i + 1].tex_coord.y = (float)(0.5 + 0.34 * sin(an - ang));
        }
        for (i = 0; i < 32; i++) {
            idx[i * 3] = 0;
            idx[i * 3 + 1] = i + 1;
            idx[i * 3 + 2] = i + 2;
        }
        SDL_RenderGeometry(renderer, pic, v, 34, idx, 32 * 3);
    } else {
        ui_fan(cx, cy, r * lab, 0, two_pi, 40, cfg_bar_r, cfg_bar_g, cfg_bar_b, a);
    }
}

static int ui_flow_target = -1;         /* the item the row is gliding to (the playing one, or one swiped to) */
static int ui_flow_last_q = -2;
static double ui_flow_pos = 0.0;        /* the item in the middle of the row, between two items while it glides */
static int64_t ui_flow_touch = 0;       /* when the row was last swiped */
static int64_t ui_flow_t = 0;
static double ui_flow_ang = 0.0;        /* how far the disc has turned */
static int ui_flow_moving = 0;
static int ui_flow_n = 0;
static int ui_flow_press = -1;          /* the cover the mouse went down on (-1 = none) */
static int ui_flow_dragging = 0;        /* 1 once the mouse has moved far enough to drag it */
static int ui_flow_px = 0, ui_flow_py = 0;      /* where the mouse went down */
static int ui_flow_mx = 0, ui_flow_my = 0;      /* where the mouse is, while dragging */
static int ui_flow_drop = -1;           /* where the dragged item lands in the queue if dropped now */
static int64_t ui_flow_edge_at = 0;     /* when the row last stepped because the mouse was at an edge */
static struct {
    SDL_Rect r;
    int idx;
} ui_flow_hit[16];                      /* the covers drawn last time, far to near, for clicks */

/* Is the queue view showing? Audio, or audio with a cover; a video file plays full screen instead. */
static int ui_vflow = 0;                /* 1 = the queue view is shown over videos too (key L) */
static int ui_flow_vmode = 0;           /* 1 while the queue view is drawn over a video: own-shape tiles, no disc */

/* The picture of a video file in its own shape (rounded corners), or NULL if it is not a video or is still being read */
static SDL_Texture *ui_cov_native(const char *path, int *w, int *h)
{
    SDL_Texture *t = NULL;
    int i;

    if (!path || !ui_cov_mu)
        return NULL;
    {
        int cw, ch;

        ui_cov_get(path, &cw, &ch);             /* also starts the reading and makes the textures, so there is no square flash first */
    }
    SDL_LockMutex(ui_cov_mu);
    for (i = 0; i < ui_cov_n; i++)
        if (!strcmp(ui_cov[i].path, path)) {
            if (ui_cov[i].state == 2 && ui_cov[i].ntex) {
                t = ui_cov[i].ntex;
                *w = ui_cov[i].nw;
                *h = ui_cov[i].nh;
            }
            break;
        }
    SDL_UnlockMutex(ui_cov_mu);
    return t;
}

/* Width divided by height of a video's picture, or 0 if it is not known (yet) */
static double ui_cov_aspect(const char *path)
{
    int w = 0, h = 0;

    return ui_cov_native(path, &w, &h) && h > 0 ? (double)w / h : 0.0;
}

/* Is the queue view showing over a video (key L)? It also shows while the video shrinks into its tile or grows back. */
static int ui_flow_video(VideoState *is)
{
    return is && (ui_vflow || ui_vflow_p > 0.002) && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&
           q_count > 0 && q_pos >= 0 && q_pos < q_count;
}

static void toggle_full_screen(VideoState *is);

/* The queue view over a video: on or off, with the same start every time */
static int ui_vflow_auto = 0;           /* 1 = a pause opened the queue view, so playing again closes it */

static void ui_vflow_set(VideoState *is, int on)
{
    if (!!ui_vflow == !!on)
        return;
    ui_vflow = on;
    ui_vflow_t = 0;
    ui_bd_key[0] = 0;                   /* the backdrop takes its colors from the picture of this moment */
    ui_flow_pos = ui_flow_target = q_pos;       /* the row starts at the playing video, no gliding in */
    ui_flow_last_q = q_pos;
    ui_flow_touch = 0;
    is->force_refresh = 1;
}

/* A tap on the tile of the video that plays: it opens full screen and plays (1 = the window goes full screen, 0 = it only fills the window) */
static int ui_tile_fs_pending = 0;      /* the window goes full screen once the video has grown back */
#define UI_TILE_TAP_FULLSCREEN 0

static void ui_tile_open(VideoState *is)
{
    if (is->paused)
        toggle_pause(is);
    ui_vflow_auto = 0;
    ui_vflow_set(is, 0);
#if UI_TILE_TAP_FULLSCREEN
    if (!is_full_screen)
        ui_tile_fs_pending = 1;         /* not at the same time as the video grows: that made it stutter */
#endif
}

static int ui_flow_on(VideoState *is)
{
    return (is && is->audio_st && q_count > 0 && q_pos >= 0 && q_pos < q_count &&
            (!is->video_st || (is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC))) || ui_flow_video(is);
}

static int ui_flow_wants_redraw(VideoState *is)
{
    return ui_flow_on(is) && (!is->paused || ui_flow_moving || ui_flow_dragging || ui_tp_on);
}

/* How far from the middle the cover at distance d sits (in widths of the middle cover). Far covers overlap a little. */
static double ui_flow_off(double B, double d)
{
    double dc = av_clipd(d, -1.0, 1.0);

    return B * ((ui_flow_vmode ? 0.74 : 0.86) * dc + 0.42 * (d - dc)) + (d > 0 && !ui_flow_vmode ? B * 0.40 * FFMIN(d, 1.0) : 0.0);    /* the right side leaves room for the disc (not for videos) */
}

/* The icon for a file with no picture, like the file manager's: a light page with an orange music note */
static void av_unused ui_flow_note(const SDL_Rect *t, int al, int md)
{
    const double two_pi = 6.28318531;
    double u = t->w / 100.0;
    SDL_Rect r;
    SDL_Vertex v[4];
    int idx[6] = { 0, 1, 2, 1, 3, 2 }, k;
    int cr = 233 * md / 255, cg = 104 * md / 255, cb = 36 * md / 255, rad = t->w / 11;
    static const double bx[4] = { 43, 77, 43, 77 }, by[4] = { 28, 20, 37, 29 };

    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 110 * al / 255);                     /* frosted glass: a light haze, */
    ui_rr_fill(t, rad);
    SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 110 * al / 255);   /* tinted with your bar color */
    ui_rr_fill(t, rad);
    ui_fan(t->x + 36 * u, t->y + 70 * u, 9 * u, 0, two_pi, 24, cr, cg, cb, al);
    ui_fan(t->x + 66 * u, t->y + 64 * u, 9 * u, 0, two_pi, 24, cr, cg, cb, al);
    SDL_SetRenderDrawColor(renderer, cr, cg, cb, al);
    r.w = FFMAX((int)(3.6 * u), 2);
    r.x = t->x + (int)(43 * u);
    r.y = t->y + (int)(30 * u);
    r.h = (int)(40 * u);
    SDL_RenderFillRect(renderer, &r);
    r.x = t->x + (int)(73 * u);
    r.y = t->y + (int)(23 * u);
    r.h = (int)(41 * u);
    SDL_RenderFillRect(renderer, &r);
    for (k = 0; k < 4; k++) {                   /* the beam joining the two stems */
        v[k].position.x = (float)(t->x + bx[k] * u);
        v[k].position.y = (float)(t->y + by[k] * u);
        v[k].color.r = (Uint8)cr;
        v[k].color.g = (Uint8)cg;
        v[k].color.b = (Uint8)cb;
        v[k].color.a = (Uint8)al;
        v[k].tex_coord.x = 0;
        v[k].tex_coord.y = 0;
    }
    SDL_RenderGeometry(renderer, NULL, v, 4, idx, 6);
}

/* One cover in the row: its picture (the bars of a video thumbnail frosted in your bar color) or the file icon */
/* The file icon as a picture, made once: a frosted tile in your bar color with an orange music note, rounded corners.
   Remade if the bar color changes. */
static SDL_Texture *ui_flow_icon(void)
{
    enum { S = 256 };
    static SDL_Texture *tex = NULL;
    static int key = -1;
    static const double qx[4] = { 43, 77, 77, 43 }, qy[4] = { 28, 20, 29, 37 };     /* the beam, clockwise */
    int k = (cfg_bar_r << 16) | (cfg_bar_g << 8) | cfg_bar_b, x, y, e;
    double u = S / 100.0, rr = S / 11.0, a1 = 0.43, a2 = 0.43, A, C[3], tint[3];
    uint8_t *px;

    if (tex && key == k)
        return tex;
    px = av_malloc((size_t)S * S * 4);
    if (!px)
        return tex;
    tint[0] = cfg_bar_r;
    tint[1] = cfg_bar_g;
    tint[2] = cfg_bar_b;
    A = a2 + a1 * (1.0 - a2);                   /* a haze of white, then your bar color, over nothing */
    for (e = 0; e < 3; e++)
        C[e] = (tint[e] * a2 + 255.0 * a1 * (1.0 - a2)) / A;
    for (y = 0; y < S; y++)
        for (x = 0; x < S; x++) {
            double fx = x + 0.5, fy = y + 0.5, nc, c, af, corner = 1.0, mn, d;
            double ox = 233, og = 104, ob = 36;
            uint8_t *p = px + ((size_t)y * S + x) * 4;

            nc = av_clipd(9 * u - hypot(fx - 36 * u, fy - 70 * u) + 0.5, 0.0, 1.0);          /* the two note heads */
            c = av_clipd(9 * u - hypot(fx - 66 * u, fy - 64 * u) + 0.5, 0.0, 1.0);
            nc = FFMAX(nc, c);
            mn = FFMIN(FFMIN(fx - 43 * u, 46.6 * u - fx), FFMIN(fy - 30 * u, 70 * u - fy));  /* the two stems */
            nc = FFMAX(nc, av_clipd(mn + 0.5, 0.0, 1.0));
            mn = FFMIN(FFMIN(fx - 73 * u, 76.6 * u - fx), FFMIN(fy - 23 * u, 64 * u - fy));
            nc = FFMAX(nc, av_clipd(mn + 0.5, 0.0, 1.0));
            mn = 1e9;                                   /* the beam joining the stems */
            for (e = 0; e < 4; e++) {
                double px0 = qx[e] * u, py0 = qy[e] * u, px1 = qx[(e + 1) % 4] * u, py1 = qy[(e + 1) % 4] * u;

                d = -((fx - px0) * (py1 - py0) - (fy - py0) * (px1 - px0)) / hypot(px1 - px0, py1 - py0);
                mn = FFMIN(mn, d);
            }
            nc = FFMAX(nc, av_clipd(mn + 0.5, 0.0, 1.0));
            af = nc + A * (1.0 - nc);
            p[0] = (uint8_t)((ox * nc + C[0] * A * (1.0 - nc)) / af);
            p[1] = (uint8_t)((og * nc + C[1] * A * (1.0 - nc)) / af);
            p[2] = (uint8_t)((ob * nc + C[2] * A * (1.0 - nc)) / af);
            if ((x < rr || x >= S - rr) && (y < rr || y >= S - rr)) {                   /* the rounded corners */
                double kx = x < rr ? rr : S - rr, ky = y < rr ? rr : S - rr;

                corner = av_clipd(rr - hypot(fx - kx, fy - ky) + 0.5, 0.0, 1.0);
            }
            p[3] = (uint8_t)(255.0 * af * corner);
        }
    if (tex)
        SDL_DestroyTexture(tex);
    tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, S, S);
    if (tex) {
        SDL_UpdateTexture(tex, NULL, px, S * 4);
        SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_BLEND);
        key = k;
    }
    av_free(px);
    return tex;
}

/* A picture drawn as a slightly turned card: the edge nearest the middle of the row is shorter (tilt is -1 for the covers
   on the left, +1 on the right, 0 in the middle, and every value between while the row glides) */
/* SDL draws a slanted edge with no smoothing, so it shows steps. A thin fringe along the top and the bottom edge fades out
   over about a pixel and smooths them. v = the vertices of the tile: n + 1 columns, the top one at 2k, the bottom one at 2k + 1. */
static void ui_quad_fringe(SDL_Texture *tex, const SDL_Vertex *v, int n)
{
    enum { MAXN = 48 };
    SDL_Vertex f[(MAXN + 1) * 4 + 8];
    int idx[MAXN * 12 + 12], k, a, b, ni, side;

    if (n > MAXN || v[0].color.a <= 40)         /* the faint shadows do not need it */
        return;
    for (k = 0; k <= n; k++) {                  /* the outline, half a pixel inside, fading to nothing a pixel outside it (along its normal) */
        int k0 = k ? k - 1 : 0, k1 = k < n ? k + 1 : n;

        for (side = 0; side < 2; side++) {      /* 0 = the top chain, 1 = the bottom chain */
            const SDL_Vertex *p = &v[k * 2 + side], *p0 = &v[k0 * 2 + side], *p1 = &v[k1 * 2 + side];
            double tx = p1->position.x - p0->position.x, ty = p1->position.y - p0->position.y;
            double len = sqrt(tx * tx + ty * ty), nx, ny;

            if (len < 1e-6) {
                nx = 0.0;
                ny = side ? 1.0 : -1.0;
            } else {
                nx = side ? -ty / len : ty / len;
                ny = side ? tx / len : -tx / len;
            }
            f[k * 4 + side * 2] = *p;
            f[k * 4 + side * 2].position.x -= (float)(0.5 * nx);
            f[k * 4 + side * 2].position.y -= (float)(0.5 * ny);
            f[k * 4 + side * 2 + 1] = *p;
            f[k * 4 + side * 2 + 1].position.x += (float)(1.0 * nx);
            f[k * 4 + side * 2 + 1].position.y += (float)(1.0 * ny);
            f[k * 4 + side * 2 + 1].color.a = 0;
        }
    }
    ni = 0;
    for (k = 0; k < n; k++) {
        a = k * 4;
        b = (k + 1) * 4;
        idx[ni++] = a;      idx[ni++] = a + 1;  idx[ni++] = b;
        idx[ni++] = a + 1;  idx[ni++] = b + 1;  idx[ni++] = b;
        idx[ni++] = a + 2;  idx[ni++] = a + 3;  idx[ni++] = b + 2;
        idx[ni++] = a + 3;  idx[ni++] = b + 3;  idx[ni++] = b + 2;
    }
    for (side = 0; side < 2; side++) {          /* the left and the right side */
        int base = (n + 1) * 4 + side * 4, col = side ? n : 0;
        float dx = side ? 1.0f : -1.0f;

        f[base] = v[col * 2];                   /* the top corner, half a pixel inside */
        f[base].position.x -= 0.5f * dx;
        f[base + 1] = v[col * 2];               /* ...and a pixel outside */
        f[base + 1].position.x += 1.0f * dx;
        f[base + 1].color.a = 0;
        f[base + 2] = v[col * 2 + 1];
        f[base + 2].position.x -= 0.5f * dx;
        f[base + 3] = v[col * 2 + 1];
        f[base + 3].position.x += 1.0f * dx;
        f[base + 3].color.a = 0;
        idx[ni++] = base;      idx[ni++] = base + 1;  idx[ni++] = base + 2;
        idx[ni++] = base + 1;  idx[ni++] = base + 3;  idx[ni++] = base + 2;
    }
    SDL_RenderGeometry(renderer, tex, f, (n + 1) * 4 + 8, idx, ni);
}

static void ui_flow_quad(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt)
{
    enum { NS = 16 };
    SDL_Vertex v[(NS + 1) * 2];
    int idx[NS * 6], k;
    double cyt = t->y + t->h / 2.0, kin = 1.0 - 0.16 * fabs(tilt);
    SDL_Color c;

    c.r = (Uint8)md;
    c.g = (Uint8)md;
    c.b = (Uint8)md;
    c.a = (Uint8)av_clip(al, 0, 255);
    for (k = 0; k <= NS; k++) {
        double u = (double)k / NS;              /* 0 at the left edge, 1 at the right */
        double f = tilt < 0 ? 1.0 - (1.0 - kin) * u : tilt > 0 ? kin + (1.0 - kin) * u : 1.0;
        double hh = t->h * f / 2.0;

        v[k * 2].position.x = (float)(t->x + t->w * u);
        v[k * 2].position.y = (float)(cyt - hh);
        v[k * 2].color = c;
        v[k * 2].tex_coord.x = (float)u;
        v[k * 2].tex_coord.y = 0.0f;
        v[k * 2 + 1].position.x = (float)(t->x + t->w * u);
        v[k * 2 + 1].position.y = (float)(cyt + hh);
        v[k * 2 + 1].color = c;
        v[k * 2 + 1].tex_coord.x = (float)u;
        v[k * 2 + 1].tex_coord.y = 1.0f;
    }
    for (k = 0; k < NS; k++) {
        idx[k * 6] = k * 2;
        idx[k * 6 + 1] = k * 2 + 1;
        idx[k * 6 + 2] = k * 2 + 2;
        idx[k * 6 + 3] = k * 2 + 1;
        idx[k * 6 + 4] = k * 2 + 3;
        idx[k * 6 + 5] = k * 2 + 2;
    }
    SDL_RenderGeometry(renderer, tex, v, (NS + 1) * 2, idx, NS * 6);
    ui_quad_fringe(tex, v, NS);
}

static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr);

static void ui_flow_tile(int idx, const SDL_Rect *tile, int al, int md, double tilt)
{
    SDL_Texture *tex;
    SDL_Rect sh;
    int cw = 0, ch = 0, k, vid;

    tex = ui_cov_native(q_items[idx], &cw, &ch);        /* a video keeps its own shape, whatever is playing */
    vid = tex != NULL;
    if (!tex)
        tex = ui_cov_get(q_items[idx], &cw, &ch);
    if (tex) {                                  /* a soft shadow in the card's own shape: the picture again, black and bigger */
        for (k = ui_shadows_on ? 3 : 0; k >= 1; k--) {
            sh.x = tile->x - k * 4;
            sh.y = tile->y - k * 4 + 7;
            sh.w = tile->w + k * 8;
            sh.h = tile->h + k * 8;
            ui_flow_quad(tex, &sh, al * 16 / 255, 0, tilt);
        }
    } else {
        tex = ui_flow_icon();                   /* no picture (yet): the file icon */
    }
    if (tex && vid)                             /* the tiles of videos have the rounded corners of the playing one */
        ui_flow_quad_round(tex, tile, al, md, tilt, FFMIN(tile->w, tile->h) / 11);
    else if (tex)
        ui_flow_quad(tex, tile, al, md, tilt);
}

/* The size of the picture of item i fitted into a sw x sh slot: a video keeps its own shape (the playing one: the shape of the
   screen it is on), covers and files with no picture fill the slot */
static void ui_flow_fit(int i, int sw, int sh, int *nw, int *nh)
{
    double asp = (i == q_pos && ui_flow_vmode && ui_live_ok && ui_live_rect.h > 0)
                 ? (double)ui_live_rect.w / ui_live_rect.h : ui_cov_aspect(q_items[i]);

    *nw = sw;
    *nh = sh;
    if (asp > 0.0) {
        *nw = asp >= 1.0 ? sw : (int)(sh * asp);
        *nh = asp >= 1.0 ? (int)(sw / asp) : sh;
    }
}

/* The slot a tile sits in. While a video plays the slots are big; a song tile keeps the smaller size it has in a row of songs */
static double ui_flow_slot(int i, double B, double W, double H)
{
    double small = FFMIN(W * 0.30, H * 0.44);

    if (ui_flow_vmode && i != q_pos && ui_cov_aspect(q_items[i]) <= 0.0 && small < B)
        return small;
    return B;
}

/* Like ui_flow_quad, but with rounded corners (radius rr): the columns are crowded near the left and right edges, where the
   corners are, and each column's top and bottom are moved in by how far the corner cuts in there */
static void ui_flow_quad_round(SDL_Texture *tex, const SDL_Rect *t, int al, int md, double tilt, int rr)
{
    enum { NA = 14, NSTR = 4, NC = NA * 2 + NSTR };     /* columns: the left corner, the straight part, the right corner */
    SDL_Vertex v[(NC + 1) * 2];
    int idx[NC * 6], k;
    double cyt = t->y + t->h / 2.0, kin = 1.0 - 0.16 * fabs(tilt);
    SDL_Color c;

    rr = av_clip(rr, 0, FFMIN(t->w, t->h) / 2);
    c.r = (Uint8)md;
    c.g = (Uint8)md;
    c.b = (Uint8)md;
    c.a = (Uint8)av_clip(al, 0, 255);
    for (k = 0; k <= NC; k++) {
        double x, dx, inset = 0.0, u, f, hh;

        if (k <= NA) {                          /* the left corner: even steps along the arc */
            double th = 1.57079632679 * k / NA;

            x = rr * (1.0 - cos(th));
            inset = rr * (1.0 - sin(th));
        } else if (k <= NA + NSTR) {            /* the straight part */
            x = rr + (t->w - 2.0 * rr) * (k - NA) / NSTR;
        } else {                                /* the right corner */
            double th = 1.57079632679 * (k - NA - NSTR) / NA;

            x = t->w - rr + rr * sin(th);
            inset = rr * (1.0 - cos(th));
        }
        dx = 0.0;
        (void)dx;
        u = x / FFMAX(t->w, 1);
        f = tilt < 0 ? 1.0 - (1.0 - kin) * u : tilt > 0 ? kin + (1.0 - kin) * u : 1.0;      /* the same tilt as the covers */
        hh = (t->h / 2.0 - inset) * f;
        v[k * 2].position.x = (float)(t->x + x);
        v[k * 2].position.y = (float)(cyt - hh);
        v[k * 2].color = c;
        v[k * 2].tex_coord.x = (float)u;
        v[k * 2].tex_coord.y = (float)(inset / FFMAX(t->h, 1));
        v[k * 2 + 1].position.x = (float)(t->x + x);
        v[k * 2 + 1].position.y = (float)(cyt + hh);
        v[k * 2 + 1].color = c;
        v[k * 2 + 1].tex_coord.x = (float)u;
        v[k * 2 + 1].tex_coord.y = (float)(1.0 - inset / FFMAX(t->h, 1));
    }
    for (k = 0; k < NC; k++) {
        idx[k * 6] = k * 2;
        idx[k * 6 + 1] = k * 2 + 1;
        idx[k * 6 + 2] = k * 2 + 2;
        idx[k * 6 + 3] = k * 2 + 1;
        idx[k * 6 + 4] = k * 2 + 3;
        idx[k * 6 + 5] = k * 2 + 2;
    }
    SDL_RenderGeometry(renderer, tex, v, (NC + 1) * 2, idx, NC * 6);
    ui_quad_fringe(tex, v, NC);
}

/* While the queue view is over a video: remember where the video is drawn full screen, and copy the frame that is on screen
   into a picture of its own (ui_live_tex), so its tile can show it, rounded, while it plays. Called from video_image_display,
   where the colors of the frame are already set up. */
static void ui_live_grab(VideoState *is, const SDL_Rect *rect, int flip)
{
    SDL_Texture *prev;
    int w, h;

    ui_live_ok = 0;
    if (!ui_flow_video(is) || !is->vid_texture || rect->w < 16 || rect->h < 16)
        return;
    ui_live_rect = *rect;
    w = FFMIN(rect->w, 1920);
    h = (int)((double)w * rect->h / rect->w);
    if (!ui_live_tex || ui_live_w != w || ui_live_h != h) {
        if (ui_live_tex)
            SDL_DestroyTexture(ui_live_tex);
        ui_live_tex = ui_make_target(w, h);
        ui_live_w = w;
        ui_live_h = h;
        if (ui_live_tex)
            SDL_SetTextureBlendMode(ui_live_tex, SDL_BLENDMODE_BLEND);
    }
    if (!ui_live_tex)
        return;
    prev = SDL_GetRenderTarget(renderer);
    SDL_SetRenderTarget(renderer, ui_live_tex);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
    SDL_RenderCopyEx(renderer, is->vid_texture, NULL, NULL, 0, NULL, flip ? SDL_FLIP_VERTICAL : 0);
    ui_xf_video_draw(is, 1);                    /* the next video fading in, inside the tile */
    SDL_SetRenderTarget(renderer, prev);
    ui_live_ok = 1;
}

/* A title drawn as part of a turned card: it hangs under the cover's lower edge and follows it (same tilt as the cover) */
static void ui_flow_title(const char *s, int px, int cx, const SDL_Rect *t, double tilt, int al)
{
    enum { NS = 12 };
    SDL_Vertex v[(NS + 1) * 2];
    int idx[NS * 6], k, w = 0, h = 0;
    SDL_Texture *tex = ui_text_tex(s, px, &w, &h);
    double cyt = t->y + t->h / 2.0, kin = 1.0 - 0.16 * fabs(tilt), left = cx - w / 2.0;
    SDL_Color c;

    if (!tex) {
        ui_label_c(cx, t->y + t->h + 18, s, px, 235, 235, 235, al);
        return;
    }
    c.r = 235;
    c.g = 235;
    c.b = 235;
    c.a = (Uint8)av_clip((int)(al * ui_fade), 0, 255);
    SDL_SetTextureColorMod(tex, 255, 255, 255);
    SDL_SetTextureAlphaMod(tex, 255);
    for (k = 0; k <= NS; k++) {
        double u = (double)k / NS, x = left + w * u;
        double uc = av_clipd((x - t->x) / (double)FFMAX(t->w, 1), 0.0, 1.0);
        double f = tilt < 0 ? 1.0 - (1.0 - kin) * uc : tilt > 0 ? kin + (1.0 - kin) * uc : 1.0;
        double mid = cyt + t->h * f / 2.0 + 18.0 * f;
        double hh = h * f / 2.0;

        v[k * 2].position.x = (float)x;
        v[k * 2].position.y = (float)(mid - hh);
        v[k * 2].color = c;
        v[k * 2].tex_coord.x = (float)u;
        v[k * 2].tex_coord.y = 0.0f;
        v[k * 2 + 1].position.x = (float)x;
        v[k * 2 + 1].position.y = (float)(mid + hh);
        v[k * 2 + 1].color = c;
        v[k * 2 + 1].tex_coord.x = (float)u;
        v[k * 2 + 1].tex_coord.y = 1.0f;
    }
    for (k = 0; k < NS; k++) {
        idx[k * 6] = k * 2;
        idx[k * 6 + 1] = k * 2 + 1;
        idx[k * 6 + 2] = k * 2 + 2;
        idx[k * 6 + 3] = k * 2 + 1;
        idx[k * 6 + 4] = k * 2 + 3;
        idx[k * 6 + 5] = k * 2 + 2;
    }
    SDL_RenderGeometry(renderer, tex, v, (NS + 1) * 2, idx, NS * 6);
}

/* The dot before the title of the item that plays: the same small bar-color dot that marks the menu row under the mouse.
   It sits just before the text that ui_flow_title draws, on the same line, tilted with the card. */
static void ui_flow_title_dot(const char *s, int px, int cx, const SDL_Rect *t, double tilt, int al, int size)
{
    double kin = 1.0 - 0.16 * fabs(tilt), x = cx - ui_text_width(s, px) / 2.0 - size - 6;
    double uc = av_clipd((x - t->x) / (double)FFMAX(t->w, 1), 0.0, 1.0);
    double f = tilt < 0 ? 1.0 - (1.0 - kin) * uc : tilt > 0 ? kin + (1.0 - kin) * uc : 1.0;
    SDL_Rect dot;

    dot.w = FFMAX((int)(size * f), 3);
    dot.h = dot.w;
    dot.x = (int)x;
    dot.y = (int)(t->y + t->h / 2.0 + t->h * f / 2.0 + 18.0 * f) - dot.h / 2;
    SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                           av_clip(cfg_bar_b + 40, 0, 255), al * 235 / 255);
    ui_pill(&dot);
}

/* ----- the shape of the whole track, read in the background -----
   Every file that plays is read once (at low priority) and measured: how loud each stretch of it is. */
#define UI_WAVE_N 200

typedef struct UiWave {
    char *path;
    int state;                  /* 0 = being read, 1 = ready, 2 = could not be read */
    float bin[UI_WAVE_N];
} UiWave;

static UiWave ui_wave[48];
static int ui_wave_n = 0, ui_wave_rr = 0;
static SDL_mutex *ui_wave_mu = NULL;
static SDL_cond *ui_wave_cv = NULL;
static int ui_wave_todo[48];
static unsigned ui_wave_head = 0, ui_wave_tail = 0;

static int ui_wave_cmp(const void *a, const void *b)
{
    float x = *(const float *)a, y = *(const float *)b;

    return x < y ? -1 : x > y;
}

/* Read all the audio of a file and measure it in UI_WAVE_N stretches. Returns 1 if bins are filled. */
static int ui_wave_scan(const char *path, float *bins)
{
    enum { RATE = 8000 };
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    AVFrame *fr = NULL;
    AVPacket *pk = NULL;
    SwrContext *swr = NULL;
    const AVCodec *codec;
    AVStream *st;
    AVChannelLayout mono = AV_CHANNEL_LAYOUT_MONO, inl;
    double acc[UI_WAVE_N] = { 0 }, dur, mx;
    long cnt[UI_WAVE_N] = { 0 };
    float tmp[UI_WAVE_N], *buf = NULL, *nbuf;
    int64_t samples = 0;
    int si, i, n, b, cap = 0, want, ret = 0;

    if (strstr(path, "://") || avformat_open_input(&ic, path, NULL, NULL) < 0)
        return 0;
    avformat_find_stream_info(ic, NULL);
    si = av_find_best_stream(ic, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
    dur = ic->duration > 0 ? ic->duration / (double)AV_TIME_BASE : 0.0;
    if (si < 0 || dur < 1.0 || dur > 7200.0)
        goto end;
    st = ic->streams[si];
    codec = avcodec_find_decoder(st->codecpar->codec_id);
    cc = codec ? avcodec_alloc_context3(codec) : NULL;
    if (!cc || avcodec_parameters_to_context(cc, st->codecpar) < 0 || avcodec_open2(cc, codec, NULL) < 0)
        goto end;
    fr = av_frame_alloc();
    pk = av_packet_alloc();
    if (!fr || !pk)
        goto end;
    while (av_read_frame(ic, pk) >= 0) {
        if (pk->stream_index == si && avcodec_send_packet(cc, pk) >= 0) {
            while (avcodec_receive_frame(cc, fr) >= 0) {
                if (!swr) {                     /* everything is turned into mono, 8000 samples a second */
                    int bad;

                    if (av_channel_layout_copy(&inl, &fr->ch_layout) < 0)
                        goto end;
                    if (inl.order == AV_CHANNEL_ORDER_UNSPEC)
                        av_channel_layout_default(&inl, inl.nb_channels > 0 ? inl.nb_channels : 2);
                    bad = swr_alloc_set_opts2(&swr, &mono, AV_SAMPLE_FMT_FLT, RATE, &inl, fr->format, fr->sample_rate, 0, NULL) < 0 ||
                          swr_init(swr) < 0;
                    av_channel_layout_uninit(&inl);
                    if (bad)
                        goto end;
                }
                want = (int)av_rescale_rnd(fr->nb_samples, RATE, FFMAX(fr->sample_rate, 1), AV_ROUND_UP) + 64;
                if (want > cap) {
                    nbuf = av_realloc_array(buf, want, sizeof(float));
                    if (!nbuf)
                        goto end;
                    buf = nbuf;
                    cap = want;
                }
                n = swr_convert(swr, (uint8_t **)&buf, cap, (const uint8_t **)fr->extended_data, fr->nb_samples);
                for (i = 0; i < n; i++) {
                    b = av_clip((int)(samples / (RATE * dur) * UI_WAVE_N), 0, UI_WAVE_N - 1);
                    acc[b] += (double)buf[i] * buf[i];
                    cnt[b]++;
                    samples++;
                }
                av_frame_unref(fr);
            }
        }
        av_packet_unref(pk);
    }
    for (i = 0; i < UI_WAVE_N; i++) {
        bins[i] = cnt[i] ? (float)sqrt(acc[i] / cnt[i]) : 0.0f;
        tmp[i] = bins[i];
    }
    qsort(tmp, UI_WAVE_N, sizeof(float), ui_wave_cmp);
    mx = tmp[(int)(UI_WAVE_N * 0.97)];          /* the loud parts reach the top; one odd peak doesn't flatten the rest */
    if (mx <= 0.0)
        goto end;
    for (i = 0; i < UI_WAVE_N; i++)
        bins[i] = (float)(1.0 - exp(-1.5 * bins[i] / mx));      /* a soft curve: louder is always a little taller, nothing is cut off */
    ret = 1;
end:
    swr_free(&swr);
    av_freep(&buf);
    av_frame_free(&fr);
    av_packet_free(&pk);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    return ret;
}

static int ui_wave_thread(void *arg)
{
    float bins[UI_WAVE_N];
    char *p;
    int k, ok;

    SDL_SetThreadPriority(SDL_THREAD_PRIORITY_LOW);
    for (;;) {
        SDL_LockMutex(ui_wave_mu);
        while (ui_wave_head >= ui_wave_tail)
            SDL_CondWait(ui_wave_cv, ui_wave_mu);
        k = ui_wave_todo[ui_wave_head++ % 48];
        p = av_strdup(ui_wave[k].path);
        SDL_UnlockMutex(ui_wave_mu);

        ok = p ? ui_wave_scan(p, bins) : 0;
        av_free(p);

        SDL_LockMutex(ui_wave_mu);
        if (ok)
            memcpy(ui_wave[k].bin, bins, sizeof(bins));
        ui_wave[k].state = ok ? 1 : 2;
        SDL_UnlockMutex(ui_wave_mu);
    }
    return 0;
}

/* The measured shape of a file: copies it into out and returns 1 if it is ready. Starts the scan the first time. */
static int ui_wave_get(const char *path, float *out)
{
    SDL_Thread *th;
    char *np;
    int i, k, slot, found = -1, ready = 0;

    if (!path)
        return 0;
    if (!ui_wave_mu) {
        ui_wave_mu = SDL_CreateMutex();
        ui_wave_cv = SDL_CreateCond();
        if (!ui_wave_mu || !ui_wave_cv)
            return 0;
        th = SDL_CreateThread(ui_wave_thread, "wave", NULL);
        if (th)
            SDL_DetachThread(th);
    }
    SDL_LockMutex(ui_wave_mu);
    for (i = 0; i < ui_wave_n; i++)
        if (ui_wave[i].path && !strcmp(ui_wave[i].path, path)) {
            found = i;
            break;
        }
    if (found < 0) {
        slot = -1;
        if (ui_wave_n < 48) {
            slot = ui_wave_n++;
        } else {
            for (i = 0; i < 48; i++) {          /* the table is full: reuse the next place that is not busy */
                k = (ui_wave_rr + i) % 48;
                if (ui_wave[k].state != 0) {
                    slot = k;
                    ui_wave_rr = (k + 1) % 48;
                    break;
                }
            }
        }
        np = slot >= 0 ? av_strdup(path) : NULL;
        if (np) {
            av_free(ui_wave[slot].path);
            ui_wave[slot].path = np;
            ui_wave[slot].state = 0;
            ui_wave_todo[ui_wave_tail++ % 48] = slot;
            SDL_CondSignal(ui_wave_cv);
            found = slot;
        } else if (slot >= 0 && slot == ui_wave_n - 1 && !ui_wave[slot].path) {
            ui_wave_n--;
        }
    }
    if (found >= 0 && ui_wave[found].state == 1) {
        memcpy(out, ui_wave[found].bin, sizeof(ui_wave[found].bin));
        ready = 1;
    }
    SDL_UnlockMutex(ui_wave_mu);
    return ready;
}

/* ---- previews on the tiles: the video under the mouse plays on its tile, without sound, at its own speed ---- */
#define UI_TILE_PREVIEW 1               /* 0 = no previews on the tiles */
#define UI_TP_W 480                     /* the width of the pictures */

static struct {
    SDL_Thread *thread;
    volatile int abort;
    SDL_mutex *mutex;
    char *file;                         /* the item that is previewed */
    int w, h;                           /* the size of the pictures (set by the thread before the first one) */
    uint8_t *rgba;                      /* the newest picture (the thread writes, the main thread reads, both under the mutex) */
    int serial, shown;                  /* counts up with each picture / the picture the texture has */
    int64_t born;                       /* when the first picture was drawn (for the fade in) */
    SDL_Texture *tex;
    int tex_w, tex_h;
} ui_tp;

static int ui_flow_cover_at(VideoState *is, int x, int y);

static int ui_tp_intr(void *p)
{
    return *(volatile int *)p;
}

/* The player of the preview: its own copy of the file, decoded on a thread, one picture at a time on the clock of the file */
static int ui_tp_run(void *arg)
{
    AVFormatContext *ic = NULL;
    AVCodecContext *cc = NULL;
    const AVCodec *dec = NULL;
    AVPacket *pk = av_packet_alloc();
    AVFrame *fr = av_frame_alloc();
    struct SwsContext *sws = NULL;
    uint8_t *buf = NULL;
    int vs, tw, th, bad = 0;
    int64_t begin = 0, wall0 = 0;
    double pts0 = NAN, last = NAN, tb;

    SDL_SetThreadPriority(SDL_THREAD_PRIORITY_LOW);
    if (!pk || !fr)
        goto end;
    ic = avformat_alloc_context();
    if (!ic)
        goto end;
    ic->interrupt_callback.callback = ui_tp_intr;
    ic->interrupt_callback.opaque = (void *)&ui_tp.abort;
    if (avformat_open_input(&ic, ui_tp.file, NULL, NULL) < 0) {
        ic = NULL;
        goto end;
    }
    if (avformat_find_stream_info(ic, NULL) < 0)
        goto end;
    vs = av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO, -1, -1, &dec, 0);
    if (vs < 0 || !dec || (ic->streams[vs]->disposition & AV_DISPOSITION_ATTACHED_PIC))
        goto end;
    cc = avcodec_alloc_context3(dec);
    if (!cc || avcodec_parameters_to_context(cc, ic->streams[vs]->codecpar) < 0)
        goto end;
    cc->thread_count = 2;
    if (avcodec_open2(cc, dec, NULL) < 0 || cc->width <= 0 || cc->height <= 0)
        goto end;
    tw = FFMIN(UI_TP_W, cc->width) & ~1;
    th = ((int)((int64_t)tw * cc->height / cc->width)) & ~1;
    if (tw < 16 || th < 16)
        goto end;
    buf = av_malloc((size_t)tw * th * 4);
    if (!buf)
        goto end;
    tb = av_q2d(ic->streams[vs]->time_base);
    if (ic->duration > 20 * (int64_t)AV_TIME_BASE)      /* a little into the video, past the first seconds */
        begin = (ic->start_time != AV_NOPTS_VALUE ? ic->start_time : 0) + ic->duration / 6;
    else
        begin = ic->start_time != AV_NOPTS_VALUE ? ic->start_time : 0;
    if (begin > 0 && av_seek_frame(ic, -1, begin, AVSEEK_FLAG_BACKWARD) >= 0)
        avcodec_flush_buffers(cc);

    while (!ui_tp.abort) {
        int ret = av_read_frame(ic, pk);

        if (ret < 0) {                          /* the end: from the start again */
            if (++bad > 3)
                break;
            if (av_seek_frame(ic, -1, begin, AVSEEK_FLAG_BACKWARD) < 0)
                break;
            avcodec_flush_buffers(cc);
            pts0 = NAN;
            continue;
        }
        if (pk->stream_index != vs || avcodec_send_packet(cc, pk) < 0) {
            av_packet_unref(pk);
            continue;
        }
        av_packet_unref(pk);
        while (!ui_tp.abort && avcodec_receive_frame(cc, fr) == 0) {
            double pts = fr->best_effort_timestamp == AV_NOPTS_VALUE ? NAN : fr->best_effort_timestamp * tb;
            int64_t due, tnow;
            uint8_t *dp[4] = { buf, NULL, NULL, NULL };
            int dl[4] = { tw * 4, 0, 0, 0 };

            if (isnan(pts))
                pts = isnan(last) ? 0.0 : last + 0.04;
            last = pts;
            bad = 0;
            if (isnan(pts0)) {
                pts0 = pts;
                wall0 = av_gettime_relative();
            }
            due = wall0 + (int64_t)((pts - pts0) * 1000000.0);
            while (!ui_tp.abort && (tnow = av_gettime_relative()) < due)
                av_usleep(FFMIN(due - tnow, 4000));
            if (ui_tp.abort)
                break;
            tnow = av_gettime_relative();
            if (tnow - due > 250000)            /* far behind: carry on from here instead of racing to catch up */
                wall0 += tnow - due;
            sws = sws_getCachedContext(sws, fr->width, fr->height, fr->format, tw, th, AV_PIX_FMT_RGBA, SWS_BILINEAR, NULL, NULL, NULL);
            if (!sws) {
                av_frame_unref(fr);
                goto end;
            }
            sws_scale(sws, (const uint8_t * const *)fr->data, fr->linesize, 0, fr->height, dp, dl);
            SDL_LockMutex(ui_tp.mutex);
            if (!ui_tp.rgba || ui_tp.w != tw || ui_tp.h != th) {
                av_freep(&ui_tp.rgba);
                ui_tp.rgba = av_malloc((size_t)tw * th * 4);
                ui_tp.w = tw;
                ui_tp.h = th;
            }
            if (ui_tp.rgba) {
                memcpy(ui_tp.rgba, buf, (size_t)tw * th * 4);
                ui_tp.serial++;
            }
            SDL_UnlockMutex(ui_tp.mutex);
            av_frame_unref(fr);
        }
    }
end:
    sws_freeContext(sws);
    av_freep(&buf);
    avcodec_free_context(&cc);
    avformat_close_input(&ic);
    av_packet_free(&pk);
    av_frame_free(&fr);
    return 0;
}

static void ui_tp_stop(void)
{
    if (ui_tp.thread) {
        ui_tp.abort = 1;
        SDL_WaitThread(ui_tp.thread, NULL);
        ui_tp.thread = NULL;
    }
    ui_tp.abort = 0;
    if (ui_tp.tex) {
        SDL_DestroyTexture(ui_tp.tex);
        ui_tp.tex = NULL;
    }
    av_freep(&ui_tp.rgba);
    av_freep(&ui_tp.file);
    ui_tp.w = ui_tp.h = ui_tp.serial = ui_tp.shown = 0;
    ui_tp.born = 0;
    ui_tp_on = 0;
}

static void ui_tp_start(int idx)
{
    ui_tp_stop();
    if (idx < 0 || idx >= q_count)
        return;
    if (!ui_tp.mutex)
        ui_tp.mutex = SDL_CreateMutex();
    ui_tp.file = av_strdup(q_items[idx]);
    if (!ui_tp.file || !ui_tp.mutex || !(ui_tp.thread = SDL_CreateThread(ui_tp_run, "tile preview", NULL)))
        av_freep(&ui_tp.file);
}

/* Once per drawing of the queue view: a video tile that the mouse rests on for a moment starts to play. Moving on to the next
   tile right after (or over the gap between two tiles) keeps it going: the next one starts at once. */
static void ui_tp_tick(VideoState *is)
{
    static int cand = -1;
    static int64_t since = 0, gone = 0, active = 0;
    int64_t now = av_gettime_relative();
    int idx = -1;

    if (UI_TILE_PREVIEW && ui_hov_x >= 0 && ui_flow_press < 0 && !ui_flow_dragging && !ui_menu_open && !ui_prefs_open) {
        int i = ui_flow_cover_at(is, ui_hov_x, ui_hov_y);

        if (i >= 0 && i < q_count && i != q_pos && ui_cov_aspect(q_items[i]) > 0.0)
            idx = i;
    }
    if (idx < 0 && cand >= 0 && ui_hov_x >= 0) {        /* off the tile for a moment (a gap, the playing tile): carry on a little */
        if (!gone)
            gone = now;
        if (now - gone < 350000)
            idx = cand;
    } else {
        gone = 0;
    }
    if (ui_tp.file)
        active = now;
    if (idx != cand) {                          /* another tile, or none: the preview stops */
        cand = idx;
        since = now;
        ui_tp_stop();
    } else if (idx >= 0 && !ui_tp.file && now - since > (now - active < 1500000 ? 0 : 400000)) {
        ui_tp_start(idx);
    }
    ui_tp_on = cand >= 0;
}

/* The preview, if it is the one of tile i: drawn over the cover, with the same turn and rounded corners */
static void ui_tp_draw(int i, const SDL_Rect *tile, int al, int md, double tilt)
{
    int64_t now = av_gettime_relative();
    double fade;

    if (!ui_tp.file || !ui_tp.mutex || strcmp(q_items[i], ui_tp.file))
        return;
    SDL_LockMutex(ui_tp.mutex);
    if (ui_tp.rgba && ui_tp.w > 0 && ui_tp.serial != ui_tp.shown) {
        if (ui_tp.tex && (ui_tp.tex_w != ui_tp.w || ui_tp.tex_h != ui_tp.h)) {
            SDL_DestroyTexture(ui_tp.tex);
            ui_tp.tex = NULL;
        }
        if (!ui_tp.tex) {
            ui_tp.tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ui_tp.w, ui_tp.h);
            ui_tp.tex_w = ui_tp.w;
            ui_tp.tex_h = ui_tp.h;
            if (ui_tp.tex)
                SDL_SetTextureBlendMode(ui_tp.tex, SDL_BLENDMODE_BLEND);
        }
        if (ui_tp.tex)
            SDL_UpdateTexture(ui_tp.tex, NULL, ui_tp.rgba, ui_tp.w * 4);
        ui_tp.shown = ui_tp.serial;
    }
    SDL_UnlockMutex(ui_tp.mutex);
    if (!ui_tp.tex)
        return;
    if (!ui_tp.born)
        ui_tp.born = now;
    fade = av_clipd((now - ui_tp.born) / 250000.0, 0.0, 1.0);
    ui_flow_quad_round(ui_tp.tex, tile, (int)(al * fade), md, tilt, FFMIN(tile->w, tile->h) / 11);
}

static void ui_flow_draw(VideoState *is)
{
    enum { NEQ = 72 };
    int sm, npx, gy;
    static float eq[NEQ], lvl = 0.0f;
    static int64_t eq_at = 0;
    int64_t now = av_gettime_relative();
    int W = is->width, H = is->height, i, j, pass, cx, cy, ci, nb, bw, maxh;
    double dt, B, d, ad, sc, off, s, t = now / 1000000.0, pitch, amp;
    SDL_Rect sk, vo, tile, bar;
    char name[320], num[48];
    int al, md, have, b0, b1, q, mid, chh, nal;
    float wv[UI_WAVE_N];

    if (!ui_flow_on(is) || W < 260 || H < 200) {
        ui_flow_n = 0;
        ui_flow_moving = 0;
        ui_tp_stop();
        return;
    }
    ui_flow_vmode = ui_flow_video(is);          /* over a video: tiles in their own shape, no disc */
    if (!ui_flow_vmode) {                       /* an audio item shows the queue view: a video that follows keeps it (L goes to the full screen video) */
        ui_vflow = 1;
        ui_vflow_p = 1.0;
        ui_vflow_ep = 1.0;
    }
    ui_tp_tick(is);
    dt = ui_flow_t ? av_clipd((now - ui_flow_t) / 1000000.0, 0.0, 0.1) : 0.0;
    ui_flow_t = now;
    {                                           /* the video shrinks into its tile (or grows back) smoothly when L is pressed */
        double want = ui_vflow ? 1.0 : 0.0, dtv = ui_vflow_t ? av_clipd((now - ui_vflow_t) / 1000000.0, 0.0, 0.1) : 0.0;

        ui_vflow_t = now;
        ui_vflow_p += (want - ui_vflow_p) * (1.0 - exp(-dtv * (want > 0.5 ? 8.0 : 12.0)));      /* growing back is quicker */
        if (fabs(want - ui_vflow_p) < 0.004)
            ui_vflow_p = want;
        ui_vflow_ep = ui_vflow_p * ui_vflow_p * (3.0 - 2.0 * ui_vflow_p);
    }
    if (q_pos != ui_flow_last_q) {              /* a new item started: the row glides to it */
        ui_flow_last_q = q_pos;
        ui_flow_target = q_pos;
        ui_flow_touch = 0;
    }
                                                /* the row stays where it was swiped to until a tap outside the tiles */
    ui_flow_target = av_clip(ui_flow_target, 0, q_count - 1);
    ui_flow_pos += (ui_flow_target - ui_flow_pos) * (1.0 - exp(-dt * 10.0));
    ui_flow_moving = fabs(ui_flow_target - ui_flow_pos) > 0.003;
    if (!ui_flow_moving)
        ui_flow_pos = ui_flow_target;
    if (ui_vflow_p != (ui_vflow ? 1.0 : 0.0))
        ui_flow_moving = 1;                     /* the video is still shrinking into its tile, or growing back: keep drawing */
    if (!is->paused)
        ui_flow_ang = fmod(ui_flow_ang + dt * 0.9, 6.28318531);        /* about one turn every 7 seconds */
    lvl += ((is->paused ? 0.0f : av_clipf(is->level * 4.0f, 0.0f, 1.0f)) - lvl) * 0.25f;
    if (now - eq_at > 45000 || now < eq_at) {
        memmove(eq, eq + 1, sizeof(float) * (NEQ - 1));
        eq[NEQ - 1] = lvl;
        eq_at = now;
    }

    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    {                                           /* video tiles: as big as the window allows (a wide picture fills the width, a tall one the height) */
        double ar = 1.0;

        if (ui_flow_vmode && is->video_st && is->video_st->codecpar->height > 0)
            ar = av_clipd((double)is->video_st->codecpar->width / is->video_st->codecpar->height, 1.0, 1.8);
        B = ui_flow_vmode ? FFMIN(W * 0.52, H * 0.58 * ar) : FFMIN(W * 0.30, H * 0.44);
    }
    cx = W / 2 - (ui_flow_vmode ? 0 : (int)(B * 0.12));
    chh = (int)B;                               /* the height of the middle tile */
    cy = (int)(H * (ui_flow_vmode ? 0.38 : 0.40));
    ui_flow_n = 0;
    ci = av_clip((int)(ui_flow_pos + 0.5), 0, q_count - 1);

    {
        SDL_Rect ui_flow_rects[11], cut, dcl;
        double tl[11];
        int ok[11];

        for (i = ci - 5; i <= ci + 5; i++) {    /* first, where every cover sits */
            int e = i - (ci - 5);

            ok[e] = i >= 0 && i < q_count;
            if (!ok[e])
                continue;
            d = i - ui_flow_pos;
            ad = fabs(d);
            sc = 1.0 - ((ui_flow_vmode && i != q_pos && ui_cov_aspect(q_items[i]) > 0.0) ? 0.16 : 0.40) * FFMIN(ad, 1.0) -
                 0.06 * FFMAX(FFMIN(ad, 3.0) - 1.0, 0.0);
            off = ui_flow_off(B, d);
            if (ui_flow_vmode && i != q_pos) {  /* the other tiles slide out from behind the video and grow a little */
                off *= 0.55 + 0.45 * ui_vflow_ep;
                sc *= 0.8 + 0.2 * ui_vflow_ep;
            }
            s = ui_flow_slot(i, B, W, H) * sc;
            tl[e] = av_clipd(d, -1.0, 1.0) * (0.45 + 1.1 * fmod(i * 0.61803398875 + 0.3, 1.0));    /* each cover turns a little differently */
            ui_flow_rects[e].w = (int)(s * (1.0 - 0.14 * fabs(tl[e])));         /* a turned cover is narrower */
            ui_flow_rects[e].h = (int)s;
            ui_flow_rects[e].x = cx + (int)(off - s / 2);
            if (d < 0)
                ui_flow_rects[e].x += (int)s - ui_flow_rects[e].w;              /* the edge nearest the middle stays put */
            ui_flow_rects[e].y = cy - (int)(s / 2);
            {                                   /* a video keeps its own shape (whatever is playing): fitted into the square slot, centred in it */
                int sw = ui_flow_rects[e].w, sh = ui_flow_rects[e].h, nw, nh;

                ui_flow_fit(i, sw, sh, &nw, &nh);
                ui_flow_rects[e].x += (sw - nw) / 2;
                ui_flow_rects[e].y += (sh - nh) / 2;
                ui_flow_rects[e].w = nw;
                ui_flow_rects[e].h = nh;
            }
        }
        {                                       /* the labels and bars go under the middle picture: its height is eased between the two nearest items, so they do not jump */
            int i0 = av_clip((int)floor(ui_flow_pos), 0, q_count - 1), i1 = FFMIN(i0 + 1, q_count - 1), pw, h0, h1;
            double f = av_clipd(ui_flow_pos - i0, 0.0, 1.0);

            ui_flow_fit(i0, (int)ui_flow_slot(i0, B, W, H), (int)ui_flow_slot(i0, B, W, H), &pw, &h0);
            ui_flow_fit(i1, (int)ui_flow_slot(i1, B, W, H), (int)ui_flow_slot(i1, B, W, H), &pw, &h1);
            chh = (int)(h0 * (1.0 - f) + h1 * f);
        }
        for (pass = 4; pass >= 0; pass--) {     /* then draw them, the far ones first */
            for (i = ci - 5; i <= ci + 5; i++) {
                int e = i - (ci - 5), vx0, vx1, vw;

                if (!ok[e] || (int)(fabs(i - ui_flow_pos) + 0.5) != pass)
                    continue;
                d = i - ui_flow_pos;
                ad = fabs(d);
                tile = ui_flow_rects[e];
                s = tile.w;
                al = (int)(255 * av_clipd(1.6 - 0.35 * ad, 0.12, 1.0));
                md = (int)(255 * av_clipd(1.0 - 0.20 * FFMIN(ad, 2.0), 0.4, 1.0));
                if (ui_flow_vmode && i != q_pos)
                    al = (int)(al * ui_vflow_ep);       /* the other tiles fade in while the video shrinks */

                vx0 = tile.x;                   /* the part of this cover that is not covered by a nearer one */
                vx1 = tile.x + tile.w;
                cut.x = 0;
                cut.y = 0;
                cut.w = W;
                cut.h = H;
                if (d < -0.5 && e + 1 < 11 && ok[e + 1]) {
                    vx1 = FFMIN(vx1, ui_flow_rects[e + 1].x);
                    cut.w = FFMAX(vx1, 0);
                } else if (d > 0.5 && e > 0 && ok[e - 1]) {
                    vx0 = FFMAX(vx0, ui_flow_rects[e - 1].x + ui_flow_rects[e - 1].w);
                    cut.x = av_clip(vx0, 0, W);
                    cut.w = W - cut.x;
                }
                vw = vx1 - vx0;
                if (vw <= 0 || cut.w <= 0)
                    continue;                   /* hidden completely */
                SDL_RenderSetClipRect(renderer, &cut);
                if (i == q_pos && !ui_flow_vmode) {     /* the disc only shows where it sticks out to the right of the cover */
                    dcl.x = FFMAX(tile.x + tile.w, cut.x);
                    dcl.y = 0;
                    dcl.w = FFMAX(cut.x + cut.w - dcl.x, 0);
                    dcl.h = H;
                    if (dcl.w > 0) {
                        SDL_Color dcol;
                        SDL_Texture *dpic = ui_cov_tone(q_items[i], &dcol);

                        SDL_RenderSetClipRect(renderer, &dcl);
                        ui_flow_disc(tile.x + s, cy, s * 0.42, ui_flow_ang, al, dpic, dcol);     /* centered on the cover's edge: a semicircle shows */
                        SDL_RenderSetClipRect(renderer, &cut);
                    }
                }
                if (ui_flow_vmode && i == q_pos && ui_live_ok) {        /* the video that plays now keeps playing in its tile */
                    SDL_Rect lr = tile;
                    double ep = ui_vflow_ep;

                    if (ep < 1.0) {             /* on its way between the full screen and its tile */
                        lr.x = ui_live_rect.x + (int)((tile.x - ui_live_rect.x) * ep);
                        lr.y = ui_live_rect.y + (int)((tile.y - ui_live_rect.y) * ep);
                        lr.w = ui_live_rect.w + (int)((tile.w - ui_live_rect.w) * ep);
                        lr.h = ui_live_rect.h + (int)((tile.h - ui_live_rect.h) * ep);
                    }
                    ui_flow_quad_round(ui_live_tex, &lr, al, md, tl[e] * ep, (int)(FFMIN(lr.w, lr.h) / 11.0 * ep));
                } else {
                    ui_flow_tile(i, &tile, (ui_flow_dragging && i == ui_flow_press) ? al / 3 : al, md, tl[e]);
                    ui_tp_draw(i, &tile, al, md, tl[e]);        /* the video under the mouse plays on its tile */
                }
                if (i != ci && vw >= 48) {      /* a small, faded title under the part that shows, tilted with its cover */
                    ui_q_name(i, name, 300);
                    ui_fit_text(name, 15, vw);
                    ui_flow_title(name, 15, vx0 + vw / 2, &tile, tl[e], al * 55 / 100);
                    if (i == q_pos)             /* the dot of the item that plays, before its title */
                        ui_flow_title_dot(name, 15, vx0 + vw / 2, &tile, tl[e], al, 6);
                }
                SDL_RenderSetClipRect(renderer, NULL);
                if (ui_flow_n < 16) {           /* a click on a hidden part goes to the cover in front */
                    ui_flow_hit[ui_flow_n].r.x = vx0;
                    ui_flow_hit[ui_flow_n].r.y = tile.y;
                    ui_flow_hit[ui_flow_n].r.w = vw;
                    ui_flow_hit[ui_flow_n].r.h = tile.h;
                    ui_flow_hit[ui_flow_n].idx = i;
                    ui_flow_n++;
                }
            }
        }
    }

    ui_q_name(ci, name, 300);                   /* the name under the middle cover */
    sm = H < 460;                               /* a small window: a smaller name, no counter, fewer bars */
    npx = sm ? 18 : 22;
    gy = cy + chh / 2 + (sm ? 26 : 40);
    ui_fit_text(name, npx, (int)(W * 0.8));
    nal = ui_flow_vmode ? (int)(255 * ui_vflow_ep) : 255;       /* the labels fade in with the tiles */
    ui_label_c(W / 2, gy, name, npx, 255, 255, 255, nal);
    if (ci == q_pos) {                          /* the dot of the item that plays, before its title */
        SDL_Rect pdot;

        pdot.w = 8;
        pdot.h = 8;
        pdot.x = W / 2 - ui_text_width(name, npx) / 2 - 20;
        pdot.y = gy - 4;
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 40, 0, 255), av_clip(cfg_bar_g + 40, 0, 255),
                               av_clip(cfg_bar_b + 40, 0, 255), (int)(235 * nal / 255));
        ui_pill(&pdot);
    }
    snprintf(num, sizeof(num), "%d / %d", ci + 1, q_count);
    if (!sm)
        ui_label_c(W / 2, cy + chh / 2 + 70, num, 15, 175, 175, 175, nal);
    {                                           /* a small hint while the row is away from the playing item (a tap outside the tiles also goes back) */
        double want = (ui_flow_target != q_pos && !ui_flow_dragging) ? 1.0 : 0.0;

        ui_flow_hint += (want - ui_flow_hint) * (1.0 - exp(-dt * 12.0));
        if (fabs(want - ui_flow_hint) < 0.01)
            ui_flow_hint = want;
        else
            ui_flow_moving = 1;                 /* keep drawing while it fades */
        if (ui_flow_hint > 0.02) {
            SDL_Rect hr;
            int hw = ui_text_width("Back to playing", 14) + 26, hy = sm ? gy + 24 : cy + chh / 2 + 70;

            hr.w = hw;
            hr.h = 24;
            hr.x = sm ? W / 2 - hw / 2 : W / 2 + ui_text_width(num, 15) / 2 + 18;
            hr.y = hy - 12;
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, (int)(95 * ui_flow_hint * nal / 255));
            ui_rr_fill(&hr, 12);
            ui_label_c(hr.x + hw / 2, hy, "Back to playing", 14, 255, 255, 255, (int)(255 * ui_flow_hint * nal / 255));
        }
    }

    {                                           /* the bars are always shown, from the left of the window to the right */
        int x0 = 24, span = W - 48, bars_ok = 1;        /* where the bars start, and how wide they spread */

        ui_layout(is, &sk, &vo);
        have = ui_wave_get(q_items[q_pos], wv);         /* the shape of the whole track, once it has been read */
        nb = FFMAX(span / 14, 24);
        pitch = (double)span / nb;
        bw = FFMAX((int)(pitch * 0.55), 2);
        {                                               /* the free space: under the name and counter, over the seek bar */
            int top = cy + chh / 2 + (sm ? 52 : 84), space = sk.y - 12 - top;

            bars_ok = space >= 18;                      /* no room (a small window): no bars, instead of bars over the name */
            mid = top + space / 2;                      /* the bars grow up and down from this line */
            maxh = av_clip(space - 12, 6, 220);         /* the tallest a bar can be */
        }
        for (j = 0; j < nb && bars_ok; j++) {
            if (have) {                                 /* the shape of the whole track, bouncing with the music */
                b0 = j * UI_WAVE_N / nb;
                b1 = FFMAX((j + 1) * UI_WAVE_N / nb, b0 + 1);
                amp = 0.0;
                for (q = b0; q < b1 && q < UI_WAVE_N; q++)
                    amp = FFMAX(amp, wv[q]);
                if (is->paused)
                    amp *= 0.9;                         /* paused: it holds still */
                else                                    /* the loudness ripple travels across the bars, as before */
                    amp = amp * (0.70 + 0.30 * fabs(sin(j * 2.3 + t * 3.7))) * (0.60 + 0.40 * eq[j * NEQ / nb]);
            } else {                                    /* not read yet: the loudness of the last few seconds */
                amp = eq[j * NEQ / nb] * (0.55 + 0.45 * fabs(sin(j * 2.3 + t * 3.7)));
            }
            bar.x = x0 + (int)(j * pitch);
            bar.h = 3 + (int)(amp * (maxh - 3));
            bar.w = bw;
            bar.y = mid - bar.h / 2;                    /* no baseline: centred on the middle line, like a sound recorder */
            SDL_SetRenderDrawColor(renderer, 255, 255, 255, 90 * nal / 255);   /* every bar the same color, as dim as the old unplayed bars */
            ui_rr_fill(&bar, bw / 2);           /* rounded top and bottom, like the seek bar */
        }
    }
    if (ui_flow_dragging && ui_flow_press >= 0 && ui_flow_press < q_count) {
        int best = -1, bd = 1 << 30, k, mid, before, p;
        SDL_Rect g;

        for (k = 0; k < ui_flow_n; k++) {       /* the cover nearest the mouse (not the one in hand) */
            if (ui_flow_hit[k].idx == ui_flow_press)
                continue;
            mid = ui_flow_hit[k].r.x + ui_flow_hit[k].r.w / 2;
            if (FFABS(ui_flow_mx - mid) < bd) {
                bd = FFABS(ui_flow_mx - mid);
                best = k;
            }
        }
        ui_flow_drop = -1;
        if (best >= 0) {
            const SDL_Rect *r = &ui_flow_hit[best].r;

            before = ui_flow_mx < r->x + r->w / 2;
            p = ui_flow_hit[best].idx + (before ? 0 : 1);       /* the place between two covers */
            ui_flow_drop = ui_flow_press < p ? p - 1 : p;
            bar.x = (before ? r->x : r->x + r->w) - 2;
            bar.y = r->y + r->h / 8;
            bar.w = 4;
            bar.h = r->h * 3 / 4;
            SDL_SetRenderDrawColor(renderer, cfg_bar_r, cfg_bar_g, cfg_bar_b, 110);       /* a quiet marker */
            ui_rr_fill(&bar, 2);
        }
        ui_flow_fit(ui_flow_press, (int)(B * 0.55), (int)(B * 0.55), &g.w, &g.h);     /* the picture in hand keeps its shape */
        g.x = ui_flow_mx - g.w / 2;
        g.y = av_clip(ui_flow_my - g.h / 2, 0, FFMAX(H - g.h, 0));
        ui_flow_tile(ui_flow_press, &g, 235, 255, 0.0);              /* the cover in hand follows the mouse */
        {
            int zone = W / 8, dist = FFMIN(ui_flow_mx, W - 1 - ui_flow_mx);    /* how far from the nearest edge */

            if (dist < zone) {                  /* in the edge zone: the closer to the very edge, the faster the row moves */
                double depth = av_clipd((zone - dist) / (double)zone, 0.0, 1.0);
                int64_t gap = 420000 - (int64_t)(360000 * depth * depth);     /* 0.42 s per step at first, 0.06 s at the edge */

                if (now - ui_flow_edge_at > gap) {
                    ui_flow_target = av_clip(ui_flow_target + (ui_flow_mx < W / 2 ? -1 : 1) * (depth > 0.9 ? 2 : 1),
                                             0, q_count - 1);
                    ui_flow_edge_at = now;
                }
            }
        }
        ui_flow_touch = now;
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Which queue item is under the mouse (the nearest cover), or -1 */
static int ui_flow_cover_at(VideoState *is, int x, int y)
{
    int i;

    if (!ui_flow_on(is) || ui_menu_open || ui_prefs_open)
        return -1;
    for (i = ui_flow_n - 1; i >= 0; i--) {      /* the last one drawn is the nearest */
        const SDL_Rect *r = &ui_flow_hit[i].r;

        if (x >= r->x && x < r->x + r->w && y >= r->y && y < r->y + r->h)
            return ui_flow_hit[i].idx;
    }
    return -1;
}

/* The mouse went down on a cover: it is a click if it comes up in the same place, a drag if it moves */
static int ui_flow_click(VideoState *is, int x, int y)
{
    int idx = ui_flow_cover_at(is, x, y);

    if (idx < 0)
        return 0;
    ui_flow_press = idx;
    ui_flow_dragging = 0;
    ui_flow_px = x;
    ui_flow_py = y;
    return 1;
}

/* The mouse moved with a cover held down. Returns 1 while a cover is held. */
/* A tap that is not on a tile: if the row was moved away from the playing item, it glides back to it (and the tap is used up) */
static int ui_flow_snap_back(VideoState *is)
{
    if (!ui_flow_on(is) || ui_flow_press >= 0 || ui_flow_dragging)
        return 0;
    if (ui_flow_target == q_pos && !ui_flow_moving)
        return 0;
    ui_flow_target = q_pos;
    ui_flow_touch = 0;
    is->force_refresh = 1;
    return 1;
}

static int ui_flow_motion(VideoState *is, int x, int y)
{
    ui_hov_x = x;
    ui_hov_y = y;
    if (ui_flow_press < 0)
        return 0;
    if (!ui_flow_dragging && (FFABS(x - ui_flow_px) >= 8 || FFABS(y - ui_flow_py) >= 8)) {
        ui_flow_dragging = 1;
        ui_flow_drop = -1;
        SDL_CaptureMouse(SDL_TRUE);
    }
    ui_flow_mx = x;
    ui_flow_my = y;
    is->force_refresh = 1;
    return 1;
}

/* The mouse came up: drop the cover where the marker is, or, if it never moved, play it (or pause / resume) */
static int ui_flow_release(VideoState *is, int x, int y)
{
    int idx = ui_flow_press;

    if (idx < 0)
        return 0;
    ui_flow_press = -1;
    if (ui_flow_dragging) {
        ui_flow_dragging = 0;
        SDL_CaptureMouse(SDL_FALSE);
        if (ui_flow_drop >= 0 && ui_flow_drop != idx && idx < q_count) {
            queue_move(idx, ui_flow_drop);
            ui_flow_last_q = q_pos;             /* the row stays on the moved item instead of jumping back */
            ui_flow_target = ui_flow_drop;
            ui_flow_touch = av_gettime_relative();
        }
        ui_flow_drop = -1;
    } else if (idx == q_pos) {
        if (ui_flow_video(is))
            ui_tile_open(is);                   /* a video: its tile opens it full screen */
        else
            toggle_pause(is);
    } else if (idx < q_count) {
        q_forced = idx;
        ui_end_current(is);
    }
    is->force_refresh = 1;
    return 1;
}

/* A sideways swipe (two fingers on the touchpad): step through the queue */
static void ui_flow_swipe(VideoState *is, SDL_Event *ev)
{
    static double acc = 0.0;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();
    double amount;
    int steps;

    if (!ui_flow_on(is) || q_count < 2)
        return;
#if SDL_VERSION_ATLEAST(2, 0, 18)
    amount = ev->wheel.preciseX;
#else
    amount = ev->wheel.x;
#endif
    if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
        amount = -amount;
    if (now - last > 300000 || amount * acc < 0.0)
        acc = 0.0;
    last = now;
    acc += amount;
    steps = (int)acc;
    if (!steps)
        return;
    acc -= steps;
    if (ui_flow_target < 0)
        ui_flow_target = q_pos;
    ui_flow_target = av_clip(ui_flow_target + steps, 0, q_count - 1);
    ui_flow_touch = now;
    is->force_refresh = 1;
}

/* The buttons on the seek bar's row: previous at the left end; next, shuffle and repeat at the right end */
static void ui_ctrl_draw(VideoState *is, const SDL_Rect *sk)
{
    int cy = sk->y + sk->h / 2, ex = sk->x + sk->w;

    (void)is;
    SDL_SetRenderDrawColor(renderer, 235, 235, 235, 215);
    {                                           /* one arrowhead each, with a small bar at its end */
        SDL_Rect stop;

        stop.w = 2;
        stop.h = 12;
        stop.y = cy - 6;
        stop.x = 34 - 9;
        SDL_RenderFillRect(renderer, &stop);    /* previous: the bar, then the arrowhead */
        ui_tri(34 - 5, cy, 9, 12, -1);
        ui_tri(ex + 16 - 4, cy, 9, 12, 1);      /* next: the arrowhead, then the bar */
        stop.x = ex + 16 + 6;
        SDL_RenderFillRect(renderer, &stop);
    }
    if (q_shuffle)
        ui_shuffle_icon(ex + 44, cy, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255),
                        av_clip(cfg_bar_b + 60, 0, 255), 255);
    else
        ui_shuffle_icon(ex + 44, cy, 235, 235, 235, 150);
    if (q_repeat)
        SDL_SetRenderDrawColor(renderer, av_clip(cfg_bar_r + 60, 0, 255), av_clip(cfg_bar_g + 60, 0, 255),
                               av_clip(cfg_bar_b + 60, 0, 255), 255);
    else
        SDL_SetRenderDrawColor(renderer, 235, 235, 235, 150);
    ui_q_line(ex + 65, cy - 5, ex + 79, cy - 5);        /* the repeat loop */
    ui_q_line(ex + 65, cy + 5, ex + 79, cy + 5);
    ui_q_line(ex + 64, cy - 4, ex + 64, cy + 4);
    ui_q_line(ex + 80, cy - 4, ex + 80, cy + 4);
    ui_tri(ex + 74, cy - 5, 7, 8, 1);
    ui_tri(ex + 63, cy + 5, 7, 8, -1);
    if (q_repeat == 2)
    {                                           /* a small 1 drawn with lines (no extra text size needed) */
        ui_q_line(ex + 73, cy - 3, ex + 73, cy + 3);
        ui_q_line(ex + 71, cy - 2, ex + 73, cy - 3);
    }
}

/* A click on one of those buttons. Returns 1 if it was one. */
static int ui_ctrl_click(VideoState *is, int x)
{
    SDL_Rect sk, vo;
    int ex;

    ui_layout(is, &sk, &vo);
    ex = sk.x + sk.w;
    if (FFABS(x - 34) <= 12) {
        q_step = -1;                            /* the main loop plays the item before this one */
        ui_end_current(is);
    } else if (FFABS(x - (ex + 16)) <= 12) {
        q_step = 1;
        ui_end_current(is);
    } else if (FFABS(x - (ex + 44)) <= 13) {
        queue_set_shuffle(!q_shuffle);
    } else if (FFABS(x - (ex + 72)) <= 13) {
        q_repeat = (q_repeat + 1) % 3;
    } else {
        return 0;
    }
    is->force_refresh = 1;
    return 1;
}

static void video_display(VideoState *is)
{
    if (!is->width)
        video_open(is);

    if (ui_win_unseen())
        return;                     /* minimized or hidden: nothing to draw */

    if (ui_menu_open || ui_prefs_open) {
        ui_glass_frame(is);         /* frosted glass over the blurred picture */
        return;
    }

    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);
    {
        int full_h = is->height;

        /* The bars float over the video, so the video uses the whole window */
        if (is->audio_st && is->show_mode != SHOW_MODE_VIDEO)
            video_audio_display(is);
        else if (is->video_st)
            video_image_display(is);
        is->height = full_h;
    }
    ui_flow_draw(is);
    ui_draw(is);
    ui_titlebar_draw(is);
    ui_menu_stream = is;
    ui_menu_draw();
    ui_present();
}

static double get_clock(Clock *c)
{
    if (*c->queue_serial != c->serial)
        return NAN;
    if (c->paused) {
        return c->pts;
    } else {
        double time = av_gettime_relative() / 1000000.0;
        return c->pts_drift + time - (time - c->last_updated) * (1.0 - c->speed);
    }
}

static void set_clock_at(Clock *c, double pts, int serial, double time)
{
    c->pts = pts;
    c->last_updated = time;
    c->pts_drift = c->pts - time;
    c->serial = serial;
}

static void set_clock(Clock *c, double pts, int serial)
{
    double time = av_gettime_relative() / 1000000.0;
    set_clock_at(c, pts, serial, time);
}

static void set_clock_speed(Clock *c, double speed)
{
    set_clock(c, get_clock(c), c->serial);
    c->speed = speed;
}

static void init_clock(Clock *c, int *queue_serial)
{
    c->speed = 1.0;
    c->paused = 0;
    c->queue_serial = queue_serial;
    set_clock(c, NAN, -1);
}

static void sync_clock_to_slave(Clock *c, Clock *slave)
{
    double clock = get_clock(c);
    double slave_clock = get_clock(slave);
    if (!isnan(slave_clock) && (isnan(clock) || fabs(clock - slave_clock) > AV_NOSYNC_THRESHOLD))
        set_clock(c, slave_clock, slave->serial);
}

static int get_master_sync_type(VideoState *is) {
    if (is->av_sync_type == AV_SYNC_VIDEO_MASTER) {
        if (is->video_st)
            return AV_SYNC_VIDEO_MASTER;
        else
            return AV_SYNC_AUDIO_MASTER;
    } else if (is->av_sync_type == AV_SYNC_AUDIO_MASTER) {
        if (is->audio_st)
            return AV_SYNC_AUDIO_MASTER;
        else
            return AV_SYNC_EXTERNAL_CLOCK;
    } else {
        return AV_SYNC_EXTERNAL_CLOCK;
    }
}

/* get the current master clock value */
static double get_master_clock(VideoState *is)
{
    double val;

    switch (get_master_sync_type(is)) {
        case AV_SYNC_VIDEO_MASTER:
            val = get_clock(&is->vidclk);
            break;
        case AV_SYNC_AUDIO_MASTER:
            val = get_clock(&is->audclk);
            break;
        default:
            val = get_clock(&is->extclk);
            break;
    }
    return val;
}

static void check_external_clock_speed(VideoState *is) {
   if (is->video_stream >= 0 && is->videoq.nb_packets <= EXTERNAL_CLOCK_MIN_FRAMES ||
       is->audio_stream >= 0 && is->audioq.nb_packets <= EXTERNAL_CLOCK_MIN_FRAMES) {
       set_clock_speed(&is->extclk, FFMAX(EXTERNAL_CLOCK_SPEED_MIN, is->extclk.speed - EXTERNAL_CLOCK_SPEED_STEP));
   } else if ((is->video_stream < 0 || is->videoq.nb_packets > EXTERNAL_CLOCK_MAX_FRAMES) &&
              (is->audio_stream < 0 || is->audioq.nb_packets > EXTERNAL_CLOCK_MAX_FRAMES)) {
       set_clock_speed(&is->extclk, FFMIN(EXTERNAL_CLOCK_SPEED_MAX, is->extclk.speed + EXTERNAL_CLOCK_SPEED_STEP));
   } else {
       double speed = is->extclk.speed;
       if (speed != 1.0)
           set_clock_speed(&is->extclk, speed + EXTERNAL_CLOCK_SPEED_STEP * (1.0 - speed) / fabs(1.0 - speed));
   }
}

/* seek in the stream */
static void stream_seek(VideoState *is, int64_t pos, int64_t rel, int by_bytes)
{
    int prec = UI_PRECISE_SEEK ? ui_precise_next : 0;

    ui_seek_last = av_gettime_relative();
    ui_precise_next = 0;
    if (!is->seek_req) {
        is->seek_pos = pos;
        is->seek_rel = rel;
        is->seek_precise = prec && !by_bytes;
        is->seek_flags &= ~AVSEEK_FLAG_BYTE;
        if (by_bytes)
            is->seek_flags |= AVSEEK_FLAG_BYTE;
        is->seek_req = 1;
        SDL_CondSignal(is->continue_read_thread);
    }
}

/* pause or resume the video */
static void stream_toggle_pause(VideoState *is)
{
    if (is->paused) {
        is->frame_timer += av_gettime_relative() / 1000000.0 - is->vidclk.last_updated;
        if (is->read_pause_return != AVERROR(ENOSYS)) {
            is->vidclk.paused = 0;
        }
        set_clock(&is->vidclk, get_clock(&is->vidclk), is->vidclk.serial);
    }
    set_clock(&is->extclk, get_clock(&is->extclk), is->extclk.serial);
    is->paused = is->audclk.paused = is->vidclk.paused = is->extclk.paused = !is->paused;
}

static void toggle_pause(VideoState *is)
{
    stream_toggle_pause(is);
    is->step = 0;
}

static void toggle_mute(VideoState *is)
{
    is->muted = !is->muted;
}

static void update_volume(VideoState *is, int sign, double step)
{
    /* Linear steps of 2 on ffplay's native 0-128 scale (step is not used) */
    (void)step;
    is->audio_volume = av_clip(is->audio_volume + sign * cfg_vol_step, 0, SDL_MIX_MAXVOLUME);
    if (sign > 0)
        is->muted = 0;
}

static void step_to_next_frame(VideoState *is)
{
    /* if the stream is paused unpause it, then step */
    if (is->paused)
        stream_toggle_pause(is);
    is->step = 1;
}

static double compute_target_delay(double delay, VideoState *is)
{
    double sync_threshold, diff = 0;

    /* update delay to follow master synchronisation source */
    if (get_master_sync_type(is) != AV_SYNC_VIDEO_MASTER) {
        /* if video is slave, we try to correct big delays by
           duplicating or deleting a frame */
        diff = get_clock(&is->vidclk) - get_master_clock(is);

        /* skip or repeat frame. We take into account the
           delay to compute the threshold. I still don't know
           if it is the best guess */
        sync_threshold = FFMAX(AV_SYNC_THRESHOLD_MIN, FFMIN(AV_SYNC_THRESHOLD_MAX, delay));
        if (!isnan(diff) && fabs(diff) < is->max_frame_duration) {
            if (diff <= -sync_threshold)
                delay = FFMAX(0, delay + diff);
            else if (diff >= sync_threshold && delay > AV_SYNC_FRAMEDUP_THRESHOLD)
                delay = delay + diff;
            else if (diff >= sync_threshold)
                delay = 2 * delay;
        }
    }

    av_log(NULL, AV_LOG_TRACE, "video: delay=%0.3f A-V=%f\n",
            delay, -diff);

    return delay;
}

static double vp_duration(VideoState *is, Frame *vp, Frame *nextvp) {
    if (vp->serial == nextvp->serial) {
        double duration = nextvp->pts - vp->pts;
        if (isnan(duration) || duration <= 0 || duration > is->max_frame_duration)
            return vp->duration;
        else
            return duration;
    } else {
        return 0.0;
    }
}

static void update_video_pts(VideoState *is, double pts, int serial)
{
    /* update current video pts */
    set_clock(&is->vidclk, pts, serial);
    sync_clock_to_slave(&is->extclk, &is->vidclk);
}

/* called to display each frame */
static void video_refresh(void *opaque, double *remaining_time)
{
    VideoState *is = opaque;
    double time;

    Frame *sp, *sp2;

    if (!is->paused && get_master_sync_type(is) == AV_SYNC_EXTERNAL_CLOCK && is->realtime)
        check_external_clock_speed(is);

    if (!display_disable && is->show_mode != SHOW_MODE_VIDEO && is->audio_st) {
        time = av_gettime_relative() / 1000000.0;
        if (is->force_refresh || is->last_vis_time + rdftspeed < time) {
            video_display(is);
            is->last_vis_time = time;
        }
        *remaining_time = FFMIN(*remaining_time, is->last_vis_time + rdftspeed - time);
    }

    if (is->video_st) {
retry:
        if (frame_queue_nb_remaining(&is->pictq) == 0) {
            // nothing to do, no picture to display in the queue
        } else {
            double last_duration, duration, delay;
            Frame *vp, *lastvp;

            /* dequeue the picture */
            lastvp = frame_queue_peek_last(&is->pictq);
            vp = frame_queue_peek(&is->pictq);

            if (vp->serial != is->videoq.serial) {
                frame_queue_next(&is->pictq);
                goto retry;
            }

            if (lastvp->serial != vp->serial)
                is->frame_timer = av_gettime_relative() / 1000000.0;

            if (is->paused)
                goto display;

            /* compute nominal last_duration */
            last_duration = vp_duration(is, lastvp, vp);
            delay = compute_target_delay(last_duration, is);

            time= av_gettime_relative()/1000000.0;
            if (time < is->frame_timer + delay) {
                *remaining_time = FFMIN(is->frame_timer + delay - time, *remaining_time);
                goto display;
            }

            is->frame_timer += delay;
            if (delay > 0 && time - is->frame_timer > AV_SYNC_THRESHOLD_MAX)
                is->frame_timer = time;

            SDL_LockMutex(is->pictq.mutex);
            if (!isnan(vp->pts))
                update_video_pts(is, vp->pts, vp->serial);
            SDL_UnlockMutex(is->pictq.mutex);

            if (frame_queue_nb_remaining(&is->pictq) > 1) {
                Frame *nextvp = frame_queue_peek_next(&is->pictq);
                duration = vp_duration(is, vp, nextvp);
                if(!is->step && (framedrop>0 || (framedrop && get_master_sync_type(is) != AV_SYNC_VIDEO_MASTER)) && time > is->frame_timer + duration){
                    is->frame_drops_late++;
                    frame_queue_next(&is->pictq);
                    goto retry;
                }
            }

            if (is->subtitle_st) {
                while (frame_queue_nb_remaining(&is->subpq) > 0) {
                    sp = frame_queue_peek(&is->subpq);

                    if (frame_queue_nb_remaining(&is->subpq) > 1)
                        sp2 = frame_queue_peek_next(&is->subpq);
                    else
                        sp2 = NULL;

                    if (sp->serial != is->subtitleq.serial
                            || (is->vidclk.pts > (sp->pts + ((float) sp->sub.end_display_time / 1000)))
                            || (sp2 && is->vidclk.pts > (sp2->pts + ((float) sp2->sub.start_display_time / 1000))))
                    {
                        if (sp->uploaded) {
                            int i;
                            for (i = 0; i < sp->sub.num_rects; i++) {
                                AVSubtitleRect *sub_rect = sp->sub.rects[i];
                                uint8_t *pixels;
                                int pitch, j;

                                if (!SDL_LockTexture(is->sub_texture, (SDL_Rect *)sub_rect, (void **)&pixels, &pitch)) {
                                    for (j = 0; j < sub_rect->h; j++, pixels += pitch)
                                        memset(pixels, 0, sub_rect->w << 2);
                                    SDL_UnlockTexture(is->sub_texture);
                                }
                            }
                        }
                        frame_queue_next(&is->subpq);
                    } else {
                        break;
                    }
                }
            }

            frame_queue_next(&is->pictq);
            is->force_refresh = 1;

            if (is->step && !is->paused)
                stream_toggle_pause(is);
        }
display:
        /* display picture */
        if (!display_disable && is->force_refresh && is->show_mode == SHOW_MODE_VIDEO && is->pictq.rindex_shown)
            video_display(is);
    }
    is->force_refresh = 0;
    if (show_status) {
        AVBPrint buf;
        static int64_t last_time;
        int64_t cur_time;
        int aqsize, vqsize, sqsize;
        double av_diff;

        cur_time = av_gettime_relative();
        if (!last_time || (cur_time - last_time) >= 30000) {
            aqsize = 0;
            vqsize = 0;
            sqsize = 0;
            if (is->audio_st)
                aqsize = is->audioq.size;
            if (is->video_st)
                vqsize = is->videoq.size;
            if (is->subtitle_st)
                sqsize = is->subtitleq.size;
            av_diff = 0;
            if (is->audio_st && is->video_st)
                av_diff = get_clock(&is->audclk) - get_clock(&is->vidclk);
            else if (is->video_st)
                av_diff = get_master_clock(is) - get_clock(&is->vidclk);
            else if (is->audio_st)
                av_diff = get_master_clock(is) - get_clock(&is->audclk);

            av_bprint_init(&buf, 0, AV_BPRINT_SIZE_AUTOMATIC);
            av_bprintf(&buf,
                      "%7.2f %s:%7.3f fd=%4d aq=%5dKB vq=%5dKB sq=%5dB f=%"PRId64"/%"PRId64"   \r",
                      get_master_clock(is),
                      (is->audio_st && is->video_st) ? "A-V" : (is->video_st ? "M-V" : (is->audio_st ? "M-A" : "   ")),
                      av_diff,
                      is->frame_drops_early + is->frame_drops_late,
                      aqsize / 1024,
                      vqsize / 1024,
                      sqsize,
                      is->video_st ? is->viddec.avctx->pts_correction_num_faulty_dts : 0,
                      is->video_st ? is->viddec.avctx->pts_correction_num_faulty_pts : 0);

            if (show_status == 1 && AV_LOG_INFO > av_log_get_level())
                fprintf(stderr, "%s", buf.str);
            else
                av_log(NULL, AV_LOG_INFO, "%s", buf.str);

            fflush(stderr);
            av_bprint_finalize(&buf, NULL);

            last_time = cur_time;
        }
    }
}

static int queue_picture(VideoState *is, AVFrame *src_frame, double pts, double duration, int64_t pos, int serial)
{
    Frame *vp;

#if defined(DEBUG_SYNC)
    printf("frame_type=%c pts=%0.3f\n",
           av_get_picture_type_char(src_frame->pict_type), pts);
#endif

    if (!(vp = frame_queue_peek_writable(&is->pictq)))
        return -1;

    vp->sar = src_frame->sample_aspect_ratio;
    vp->uploaded = 0;

    vp->width = src_frame->width;
    vp->height = src_frame->height;
    vp->format = src_frame->format;

    vp->pts = pts;
    vp->duration = duration;
    vp->pos = pos;
    vp->serial = serial;

    set_default_window_size(vp->width, vp->height, vp->sar);

    av_frame_move_ref(vp->frame, src_frame);
    frame_queue_push(&is->pictq);
    return 0;
}

/* After an exact seek: pictures and sound before the wanted time are thrown away */
static int ui_prec_skip_v(VideoState *is, double pts)
{
    if (!is->prec_v || is->viddec.pkt_serial != is->prec_ser_v || isnan(pts))
        return 0;
    if (pts + 0.001 < is->prec_target)
        return 1;
    is->prec_v = 0;
    return 0;
}

static int ui_prec_skip_a(VideoState *is, AVFrame *frame)
{
    double end;

    if (!is->prec_a || is->auddec.pkt_serial != is->prec_ser_a || frame->pts == AV_NOPTS_VALUE || frame->sample_rate <= 0)
        return 0;
    end = (frame->pts + frame->nb_samples) / (double)frame->sample_rate;
    if (end <= is->prec_target)
        return 1;
    is->prec_a = 0;
    return 0;
}

static int get_video_frame(VideoState *is, AVFrame *frame)
{
    int got_picture;

    if ((got_picture = decoder_decode_frame(&is->viddec, frame, NULL)) < 0)
        return -1;

    if (got_picture) {
        double dpts = NAN;

        if (frame->pts != AV_NOPTS_VALUE)
            dpts = av_q2d(is->video_st->time_base) * frame->pts;

        frame->sample_aspect_ratio = av_guess_sample_aspect_ratio(is->ic, is->video_st, frame);

        if (ui_prec_skip_v(is, dpts)) {
            av_frame_unref(frame);
            return 0;
        }

        if (framedrop>0 || (framedrop && get_master_sync_type(is) != AV_SYNC_VIDEO_MASTER)) {
            if (frame->pts != AV_NOPTS_VALUE) {
                double diff = dpts - get_master_clock(is);
                if (!isnan(diff) && fabs(diff) < AV_NOSYNC_THRESHOLD &&
                    diff - is->frame_last_filter_delay < 0 &&
                    is->viddec.pkt_serial == is->vidclk.serial &&
                    is->videoq.nb_packets) {
                    is->frame_drops_early++;
                    av_frame_unref(frame);
                    got_picture = 0;
                }
            }
        }
    }

    return got_picture;
}

static int configure_filtergraph(AVFilterGraph *graph, const char *filtergraph,
                                 AVFilterContext *source_ctx, AVFilterContext *sink_ctx)
{
    int ret, i;
    int nb_filters = graph->nb_filters;
    AVFilterInOut *outputs = NULL, *inputs = NULL;

    if (filtergraph) {
        outputs = avfilter_inout_alloc();
        inputs  = avfilter_inout_alloc();
        if (!outputs || !inputs) {
            ret = AVERROR(ENOMEM);
            goto fail;
        }

        outputs->name       = av_strdup("in");
        outputs->filter_ctx = source_ctx;
        outputs->pad_idx    = 0;
        outputs->next       = NULL;

        inputs->name        = av_strdup("out");
        inputs->filter_ctx  = sink_ctx;
        inputs->pad_idx     = 0;
        inputs->next        = NULL;

        if ((ret = avfilter_graph_parse_ptr(graph, filtergraph, &inputs, &outputs, NULL)) < 0)
            goto fail;
    } else {
        if ((ret = avfilter_link(source_ctx, 0, sink_ctx, 0)) < 0)
            goto fail;
    }

    /* Reorder the filters to ensure that inputs of the custom filters are merged first */
    for (i = 0; i < graph->nb_filters - nb_filters; i++)
        FFSWAP(AVFilterContext*, graph->filters[i], graph->filters[i + nb_filters]);

    ret = avfilter_graph_config(graph, NULL);
fail:
    avfilter_inout_free(&outputs);
    avfilter_inout_free(&inputs);
    return ret;
}

static int configure_video_filters(AVFilterGraph *graph, VideoState *is, const char *vfilters, AVFrame *frame)
{
    enum AVPixelFormat pix_fmts[FF_ARRAY_ELEMS(sdl_texture_format_map)];
    char sws_flags_str[512] = "";
    char buffersrc_args[256];
    int ret;
    AVFilterContext *filt_src = NULL, *filt_out = NULL, *last_filter = NULL;
    AVCodecParameters *codecpar = is->video_st->codecpar;
    AVRational fr = av_guess_frame_rate(is->ic, is->video_st, NULL);
    const AVDictionaryEntry *e = NULL;
    int nb_pix_fmts = 0;
    int i, j;

    for (i = 0; i < renderer_info.num_texture_formats; i++) {
        for (j = 0; j < FF_ARRAY_ELEMS(sdl_texture_format_map) - 1; j++) {
            if (renderer_info.texture_formats[i] == sdl_texture_format_map[j].texture_fmt) {
                pix_fmts[nb_pix_fmts++] = sdl_texture_format_map[j].format;
                break;
            }
        }
    }
    pix_fmts[nb_pix_fmts] = AV_PIX_FMT_NONE;

    while ((e = av_dict_iterate(sws_dict, e))) {
        if (!strcmp(e->key, "sws_flags")) {
            av_strlcatf(sws_flags_str, sizeof(sws_flags_str), "%s=%s:", "flags", e->value);
        } else
            av_strlcatf(sws_flags_str, sizeof(sws_flags_str), "%s=%s:", e->key, e->value);
    }
    if (strlen(sws_flags_str))
        sws_flags_str[strlen(sws_flags_str)-1] = '\0';

    graph->scale_sws_opts = av_strdup(sws_flags_str);

    snprintf(buffersrc_args, sizeof(buffersrc_args),
             "video_size=%dx%d:pix_fmt=%d:time_base=%d/%d:pixel_aspect=%d/%d",
             frame->width, frame->height, frame->format,
             is->video_st->time_base.num, is->video_st->time_base.den,
             codecpar->sample_aspect_ratio.num, FFMAX(codecpar->sample_aspect_ratio.den, 1));
    if (fr.num && fr.den)
        av_strlcatf(buffersrc_args, sizeof(buffersrc_args), ":frame_rate=%d/%d", fr.num, fr.den);

    if ((ret = avfilter_graph_create_filter(&filt_src,
                                            avfilter_get_by_name("buffer"),
                                            "ffplay_buffer", buffersrc_args, NULL,
                                            graph)) < 0)
        goto fail;

    ret = avfilter_graph_create_filter(&filt_out,
                                       avfilter_get_by_name("buffersink"),
                                       "ffplay_buffersink", NULL, NULL, graph);
    if (ret < 0)
        goto fail;

    if ((ret = av_opt_set_int_list(filt_out, "pix_fmts", pix_fmts,  AV_PIX_FMT_NONE, AV_OPT_SEARCH_CHILDREN)) < 0)
        goto fail;

    last_filter = filt_out;

/* Note: this macro adds a filter before the lastly added filter, so the
 * processing order of the filters is in reverse */
#define INSERT_FILT(name, arg) do {                                          \
    AVFilterContext *filt_ctx;                                               \
                                                                             \
    ret = avfilter_graph_create_filter(&filt_ctx,                            \
                                       avfilter_get_by_name(name),           \
                                       "ffplay_" name, arg, NULL, graph);    \
    if (ret < 0)                                                             \
        goto fail;                                                           \
                                                                             \
    ret = avfilter_link(filt_ctx, 0, last_filter, 0);                        \
    if (ret < 0)                                                             \
        goto fail;                                                           \
                                                                             \
    last_filter = filt_ctx;                                                  \
} while (0)

    if (autorotate) {
        double theta = 0.0;
        int32_t *displaymatrix = NULL;
        AVFrameSideData *sd = av_frame_get_side_data(frame, AV_FRAME_DATA_DISPLAYMATRIX);
        if (sd)
            displaymatrix = (int32_t *)sd->data;
        if (!displaymatrix) {
            const AVPacketSideData *sd = av_packet_side_data_get(is->video_st->codecpar->coded_side_data,
                                                                 is->video_st->codecpar->nb_coded_side_data,
                                                                 AV_PKT_DATA_DISPLAYMATRIX);
            if (sd)
                displaymatrix = (int32_t *)sd->data;
        }
        theta = get_rotation(displaymatrix);

        if (fabs(theta - 90) < 1.0) {
            INSERT_FILT("transpose", "clock");
        } else if (fabs(theta - 180) < 1.0) {
            INSERT_FILT("hflip", NULL);
            INSERT_FILT("vflip", NULL);
        } else if (fabs(theta - 270) < 1.0) {
            INSERT_FILT("transpose", "cclock");
        } else if (fabs(theta) > 1.0) {
            char rotate_buf[64];
            snprintf(rotate_buf, sizeof(rotate_buf), "%f*PI/180", theta);
            INSERT_FILT("rotate", rotate_buf);
        }
    }

    if ((ret = configure_filtergraph(graph, vfilters, filt_src, last_filter)) < 0)
        goto fail;

    is->in_video_filter  = filt_src;
    is->out_video_filter = filt_out;

fail:
    return ret;
}

static int configure_audio_filters(VideoState *is, const char *afilters, int force_output_format)
{
    static const enum AVSampleFormat sample_fmts[] = { AV_SAMPLE_FMT_S16, AV_SAMPLE_FMT_NONE };
    int sample_rates[2] = { 0, -1 };
    AVFilterContext *filt_asrc = NULL, *filt_asink = NULL;
    char aresample_swr_opts[512] = "";
    const AVDictionaryEntry *e = NULL;
    AVBPrint bp;
    char asrc_args[256];
    int ret;

    avfilter_graph_free(&is->agraph);
    if (!(is->agraph = avfilter_graph_alloc()))
        return AVERROR(ENOMEM);
    is->agraph->nb_threads = filter_nbthreads;

    av_bprint_init(&bp, 0, AV_BPRINT_SIZE_AUTOMATIC);

    while ((e = av_dict_iterate(swr_opts, e)))
        av_strlcatf(aresample_swr_opts, sizeof(aresample_swr_opts), "%s=%s:", e->key, e->value);
    if (strlen(aresample_swr_opts))
        aresample_swr_opts[strlen(aresample_swr_opts)-1] = '\0';
    av_opt_set(is->agraph, "aresample_swr_opts", aresample_swr_opts, 0);

    av_channel_layout_describe_bprint(&is->audio_filter_src.ch_layout, &bp);

    ret = snprintf(asrc_args, sizeof(asrc_args),
                   "sample_rate=%d:sample_fmt=%s:time_base=%d/%d:channel_layout=%s",
                   is->audio_filter_src.freq, av_get_sample_fmt_name(is->audio_filter_src.fmt),
                   1, is->audio_filter_src.freq, bp.str);

    ret = avfilter_graph_create_filter(&filt_asrc,
                                       avfilter_get_by_name("abuffer"), "ffplay_abuffer",
                                       asrc_args, NULL, is->agraph);
    if (ret < 0)
        goto end;


    ret = avfilter_graph_create_filter(&filt_asink,
                                       avfilter_get_by_name("abuffersink"), "ffplay_abuffersink",
                                       NULL, NULL, is->agraph);
    if (ret < 0)
        goto end;

    if ((ret = av_opt_set_int_list(filt_asink, "sample_fmts", sample_fmts,  AV_SAMPLE_FMT_NONE, AV_OPT_SEARCH_CHILDREN)) < 0)
        goto end;
    if ((ret = av_opt_set_int(filt_asink, "all_channel_counts", 1, AV_OPT_SEARCH_CHILDREN)) < 0)
        goto end;

    if (force_output_format) {
        sample_rates   [0] = is->audio_tgt.freq;
        if ((ret = av_opt_set_int(filt_asink, "all_channel_counts", 0, AV_OPT_SEARCH_CHILDREN)) < 0)
            goto end;
        if ((ret = av_opt_set(filt_asink, "ch_layouts", bp.str, AV_OPT_SEARCH_CHILDREN)) < 0)
            goto end;
        if ((ret = av_opt_set_int_list(filt_asink, "sample_rates"   , sample_rates   ,  -1, AV_OPT_SEARCH_CHILDREN)) < 0)
            goto end;
    }


    if ((ret = configure_filtergraph(is->agraph, afilters, filt_asrc, filt_asink)) < 0)
        goto end;

    is->in_audio_filter  = filt_asrc;
    is->out_audio_filter = filt_asink;

end:
    if (ret < 0)
        avfilter_graph_free(&is->agraph);
    av_bprint_finalize(&bp, NULL);

    return ret;
}

static int audio_thread(void *arg)
{
    VideoState *is = arg;
    AVFrame *frame = av_frame_alloc();
    Frame *af;
    int last_serial = -1;
    int reconfigure;
    int got_frame = 0;
    AVRational tb;
    int ret = 0;

    if (!frame)
        return AVERROR(ENOMEM);

    do {
        if ((got_frame = decoder_decode_frame(&is->auddec, frame, NULL)) < 0)
            goto the_end;

        if (got_frame && ui_prec_skip_a(is, frame)) {
            av_frame_unref(frame);
            got_frame = 0;
        }

        if (got_frame) {
                tb = (AVRational){1, frame->sample_rate};

                reconfigure =
                    cmp_audio_fmts(is->audio_filter_src.fmt, is->audio_filter_src.ch_layout.nb_channels,
                                   frame->format, frame->ch_layout.nb_channels)    ||
                    av_channel_layout_compare(&is->audio_filter_src.ch_layout, &frame->ch_layout) ||
                    is->audio_filter_src.freq           != frame->sample_rate ||
                    is->auddec.pkt_serial               != last_serial;

                if (reconfigure) {
                    char buf1[1024], buf2[1024];
                    av_channel_layout_describe(&is->audio_filter_src.ch_layout, buf1, sizeof(buf1));
                    av_channel_layout_describe(&frame->ch_layout, buf2, sizeof(buf2));
                    av_log(NULL, AV_LOG_DEBUG,
                           "Audio frame changed from rate:%d ch:%d fmt:%s layout:%s serial:%d to rate:%d ch:%d fmt:%s layout:%s serial:%d\n",
                           is->audio_filter_src.freq, is->audio_filter_src.ch_layout.nb_channels, av_get_sample_fmt_name(is->audio_filter_src.fmt), buf1, last_serial,
                           frame->sample_rate, frame->ch_layout.nb_channels, av_get_sample_fmt_name(frame->format), buf2, is->auddec.pkt_serial);

                    is->audio_filter_src.fmt            = frame->format;
                    ret = av_channel_layout_copy(&is->audio_filter_src.ch_layout, &frame->ch_layout);
                    if (ret < 0)
                        goto the_end;
                    is->audio_filter_src.freq           = frame->sample_rate;
                    last_serial                         = is->auddec.pkt_serial;

                    if ((ret = configure_audio_filters(is, afilters, 1)) < 0)
                        goto the_end;
                }

            if ((ret = av_buffersrc_add_frame(is->in_audio_filter, frame)) < 0)
                goto the_end;

            while ((ret = av_buffersink_get_frame_flags(is->out_audio_filter, frame, 0)) >= 0) {
                FrameData *fd = frame->opaque_ref ? (FrameData*)frame->opaque_ref->data : NULL;
                tb = av_buffersink_get_time_base(is->out_audio_filter);
                if (!(af = frame_queue_peek_writable(&is->sampq)))
                    goto the_end;

                af->pts = (frame->pts == AV_NOPTS_VALUE) ? NAN : frame->pts * av_q2d(tb);
                af->pos = fd ? fd->pkt_pos : -1;
                af->serial = is->auddec.pkt_serial;
                af->duration = av_q2d((AVRational){frame->nb_samples, frame->sample_rate});

                av_frame_move_ref(af->frame, frame);
                frame_queue_push(&is->sampq);

                if (is->audioq.serial != is->auddec.pkt_serial)
                    break;
            }
            if (ret == AVERROR_EOF)
                is->auddec.finished = is->auddec.pkt_serial;
        }
    } while (ret >= 0 || ret == AVERROR(EAGAIN) || ret == AVERROR_EOF);
 the_end:
    avfilter_graph_free(&is->agraph);
    av_frame_free(&frame);
    return ret;
}

static int decoder_start(Decoder *d, int (*fn)(void *), const char *thread_name, void* arg)
{
    packet_queue_start(d->queue);
    d->decoder_tid = SDL_CreateThread(fn, thread_name, arg);
    if (!d->decoder_tid) {
        av_log(NULL, AV_LOG_ERROR, "SDL_CreateThread(): %s\n", SDL_GetError());
        return AVERROR(ENOMEM);
    }
    return 0;
}

static int video_thread(void *arg)
{
    VideoState *is = arg;
    AVFrame *frame = av_frame_alloc();
    double pts;
    double duration;
    int ret;
    AVRational tb = is->video_st->time_base;
    AVRational frame_rate = av_guess_frame_rate(is->ic, is->video_st, NULL);

    AVFilterGraph *graph = NULL;
    AVFilterContext *filt_out = NULL, *filt_in = NULL;
    int last_w = 0;
    int last_h = 0;
    enum AVPixelFormat last_format = -2;
    int last_serial = -1;
    int last_vfilter_idx = 0;

    if (!frame)
        return AVERROR(ENOMEM);

    for (;;) {
        ret = get_video_frame(is, frame);
        if (ret < 0)
            goto the_end;
        if (!ret)
            continue;

        if (   last_w != frame->width
            || last_h != frame->height
            || last_format != frame->format
            || last_serial != is->viddec.pkt_serial
            || last_vfilter_idx != is->vfilter_idx) {
            av_log(NULL, AV_LOG_DEBUG,
                   "Video frame changed from size:%dx%d format:%s serial:%d to size:%dx%d format:%s serial:%d\n",
                   last_w, last_h,
                   (const char *)av_x_if_null(av_get_pix_fmt_name(last_format), "none"), last_serial,
                   frame->width, frame->height,
                   (const char *)av_x_if_null(av_get_pix_fmt_name(frame->format), "none"), is->viddec.pkt_serial);
            avfilter_graph_free(&graph);
            graph = avfilter_graph_alloc();
            if (!graph) {
                ret = AVERROR(ENOMEM);
                goto the_end;
            }
            graph->nb_threads = filter_nbthreads;
            if ((ret = configure_video_filters(graph, is, vfilters_list ? vfilters_list[is->vfilter_idx] : NULL, frame)) < 0) {
                SDL_Event event;
                event.type = FF_QUIT_EVENT;
                event.user.data1 = is;
                SDL_PushEvent(&event);
                goto the_end;
            }
            filt_in  = is->in_video_filter;
            filt_out = is->out_video_filter;
            last_w = frame->width;
            last_h = frame->height;
            last_format = frame->format;
            last_serial = is->viddec.pkt_serial;
            last_vfilter_idx = is->vfilter_idx;
            frame_rate = av_buffersink_get_frame_rate(filt_out);
        }

        ret = av_buffersrc_add_frame(filt_in, frame);
        if (ret < 0)
            goto the_end;

        while (ret >= 0) {
            FrameData *fd;

            is->frame_last_returned_time = av_gettime_relative() / 1000000.0;

            ret = av_buffersink_get_frame_flags(filt_out, frame, 0);
            if (ret < 0) {
                if (ret == AVERROR_EOF)
                    is->viddec.finished = is->viddec.pkt_serial;
                ret = 0;
                break;
            }

            fd = frame->opaque_ref ? (FrameData*)frame->opaque_ref->data : NULL;

            is->frame_last_filter_delay = av_gettime_relative() / 1000000.0 - is->frame_last_returned_time;
            if (fabs(is->frame_last_filter_delay) > AV_NOSYNC_THRESHOLD / 10.0)
                is->frame_last_filter_delay = 0;
            tb = av_buffersink_get_time_base(filt_out);
            duration = (frame_rate.num && frame_rate.den ? av_q2d((AVRational){frame_rate.den, frame_rate.num}) : 0);
            pts = (frame->pts == AV_NOPTS_VALUE) ? NAN : frame->pts * av_q2d(tb);
            ret = queue_picture(is, frame, pts, duration, fd ? fd->pkt_pos : -1, is->viddec.pkt_serial);
            av_frame_unref(frame);
            if (is->videoq.serial != is->viddec.pkt_serial)
                break;
        }

        if (ret < 0)
            goto the_end;
    }
 the_end:
    avfilter_graph_free(&graph);
    av_frame_free(&frame);
    return 0;
}

static int subtitle_thread(void *arg)
{
    VideoState *is = arg;
    Frame *sp;
    int got_subtitle;
    double pts;

    for (;;) {
        if (!(sp = frame_queue_peek_writable(&is->subpq)))
            return 0;

        if ((got_subtitle = decoder_decode_frame(&is->subdec, NULL, &sp->sub)) < 0)
            break;

        pts = 0;

        if (got_subtitle && sp->sub.format == 0) {
            if (sp->sub.pts != AV_NOPTS_VALUE)
                pts = sp->sub.pts / (double)AV_TIME_BASE;
            sp->pts = pts;
            sp->serial = is->subdec.pkt_serial;
            sp->width = is->subdec.avctx->width;
            sp->height = is->subdec.avctx->height;
            sp->uploaded = 0;

            /* now we can update the picture count */
            frame_queue_push(&is->subpq);
        } else if (got_subtitle) {
            avsubtitle_free(&sp->sub);
        }
    }
    return 0;
}

/* copy samples for viewing in editor window */
static void update_sample_display(VideoState *is, short *samples, int samples_size)
{
    int size, len;

    size = samples_size / sizeof(short);
    while (size > 0) {
        len = SAMPLE_ARRAY_SIZE - is->sample_array_index;
        if (len > size)
            len = size;
        memcpy(is->sample_array + is->sample_array_index, samples, len * sizeof(short));
        samples += len;
        is->sample_array_index += len;
        if (is->sample_array_index >= SAMPLE_ARRAY_SIZE)
            is->sample_array_index = 0;
        size -= len;
    }
}

/* return the wanted number of samples to get better sync if sync_type is video
 * or external master clock */
static int synchronize_audio(VideoState *is, int nb_samples)
{
    int wanted_nb_samples = nb_samples;

    /* if not master, then we try to remove or add samples to correct the clock */
    if (get_master_sync_type(is) != AV_SYNC_AUDIO_MASTER) {
        double diff, avg_diff;
        int min_nb_samples, max_nb_samples;

        diff = get_clock(&is->audclk) - get_master_clock(is);

        if (!isnan(diff) && fabs(diff) < AV_NOSYNC_THRESHOLD) {
            is->audio_diff_cum = diff + is->audio_diff_avg_coef * is->audio_diff_cum;
            if (is->audio_diff_avg_count < AUDIO_DIFF_AVG_NB) {
                /* not enough measures to have a correct estimate */
                is->audio_diff_avg_count++;
            } else {
                /* estimate the A-V difference */
                avg_diff = is->audio_diff_cum * (1.0 - is->audio_diff_avg_coef);

                if (fabs(avg_diff) >= is->audio_diff_threshold) {
                    wanted_nb_samples = nb_samples + (int)(diff * is->audio_src.freq);
                    min_nb_samples = ((nb_samples * (100 - SAMPLE_CORRECTION_PERCENT_MAX) / 100));
                    max_nb_samples = ((nb_samples * (100 + SAMPLE_CORRECTION_PERCENT_MAX) / 100));
                    wanted_nb_samples = av_clip(wanted_nb_samples, min_nb_samples, max_nb_samples);
                }
                av_log(NULL, AV_LOG_TRACE, "diff=%f adiff=%f sample_diff=%d apts=%0.3f %f\n",
                        diff, avg_diff, wanted_nb_samples - nb_samples,
                        is->audio_clock, is->audio_diff_threshold);
            }
        } else {
            /* too big difference : may be initial PTS errors, so
               reset A-V filter */
            is->audio_diff_avg_count = 0;
            is->audio_diff_cum       = 0;
        }
    }

    return wanted_nb_samples;
}

/**
 * Decode one audio frame and return its uncompressed size.
 *
 * The processed audio frame is decoded, converted if required, and
 * stored in is->audio_buf, with size in bytes given by the return
 * value.
 */
static int audio_decode_frame(VideoState *is)
{
    int data_size, resampled_data_size;
    av_unused double audio_clock0;
    int wanted_nb_samples;
    Frame *af;

    if (is->paused)
        return -1;

    do {
#if defined(_WIN32)
        while (frame_queue_nb_remaining(&is->sampq) == 0) {
            if ((av_gettime_relative() - audio_callback_time) > 1000000LL * is->audio_hw_buf_size / is->audio_tgt.bytes_per_sec / 2)
                return -1;
            av_usleep (1000);
        }
#endif
        if (!(af = frame_queue_peek_readable(&is->sampq)))
            return -1;
        frame_queue_next(&is->sampq);
    } while (af->serial != is->audioq.serial);

    data_size = av_samples_get_buffer_size(NULL, af->frame->ch_layout.nb_channels,
                                           af->frame->nb_samples,
                                           af->frame->format, 1);

    wanted_nb_samples = synchronize_audio(is, af->frame->nb_samples);

    if (af->frame->format        != is->audio_src.fmt            ||
        av_channel_layout_compare(&af->frame->ch_layout, &is->audio_src.ch_layout) ||
        af->frame->sample_rate   != is->audio_src.freq           ||
        (wanted_nb_samples       != af->frame->nb_samples && !is->swr_ctx)) {
        swr_free(&is->swr_ctx);
        swr_alloc_set_opts2(&is->swr_ctx,
                            &is->audio_tgt.ch_layout, is->audio_tgt.fmt, is->audio_tgt.freq,
                            &af->frame->ch_layout, af->frame->format, af->frame->sample_rate,
                            0, NULL);
        if (!is->swr_ctx || swr_init(is->swr_ctx) < 0) {
            av_log(NULL, AV_LOG_ERROR,
                   "Cannot create sample rate converter for conversion of %d Hz %s %d channels to %d Hz %s %d channels!\n",
                    af->frame->sample_rate, av_get_sample_fmt_name(af->frame->format), af->frame->ch_layout.nb_channels,
                    is->audio_tgt.freq, av_get_sample_fmt_name(is->audio_tgt.fmt), is->audio_tgt.ch_layout.nb_channels);
            swr_free(&is->swr_ctx);
            return -1;
        }
        if (av_channel_layout_copy(&is->audio_src.ch_layout, &af->frame->ch_layout) < 0)
            return -1;
        is->audio_src.freq = af->frame->sample_rate;
        is->audio_src.fmt = af->frame->format;
    }

    if (is->swr_ctx) {
        const uint8_t **in = (const uint8_t **)af->frame->extended_data;
        uint8_t **out = &is->audio_buf1;
        int out_count = (int64_t)wanted_nb_samples * is->audio_tgt.freq / af->frame->sample_rate + 256;
        int out_size  = av_samples_get_buffer_size(NULL, is->audio_tgt.ch_layout.nb_channels, out_count, is->audio_tgt.fmt, 0);
        int len2;
        if (out_size < 0) {
            av_log(NULL, AV_LOG_ERROR, "av_samples_get_buffer_size() failed\n");
            return -1;
        }
        if (wanted_nb_samples != af->frame->nb_samples) {
            if (swr_set_compensation(is->swr_ctx, (wanted_nb_samples - af->frame->nb_samples) * is->audio_tgt.freq / af->frame->sample_rate,
                                        wanted_nb_samples * is->audio_tgt.freq / af->frame->sample_rate) < 0) {
                av_log(NULL, AV_LOG_ERROR, "swr_set_compensation() failed\n");
                return -1;
            }
        }
        av_fast_malloc(&is->audio_buf1, &is->audio_buf1_size, out_size);
        if (!is->audio_buf1)
            return AVERROR(ENOMEM);
        len2 = swr_convert(is->swr_ctx, out, out_count, in, af->frame->nb_samples);
        if (len2 < 0) {
            av_log(NULL, AV_LOG_ERROR, "swr_convert() failed\n");
            return -1;
        }
        if (len2 == out_count) {
            av_log(NULL, AV_LOG_WARNING, "audio buffer is probably too small\n");
            if (swr_init(is->swr_ctx) < 0)
                swr_free(&is->swr_ctx);
        }
        is->audio_buf = is->audio_buf1;
        resampled_data_size = len2 * is->audio_tgt.ch_layout.nb_channels * av_get_bytes_per_sample(is->audio_tgt.fmt);
    } else {
        is->audio_buf = af->frame->data[0];
        resampled_data_size = data_size;
    }

    audio_clock0 = is->audio_clock;
    /* update the audio clock with the pts */
    if (!isnan(af->pts))
        is->audio_clock = af->pts + (double) af->frame->nb_samples / af->frame->sample_rate;
    else
        is->audio_clock = NAN;
    is->audio_clock_serial = af->serial;
#ifdef DEBUG
    {
        static double last_clock;
        printf("audio: delay=%0.3f clock=%0.3f clock0=%0.3f\n",
               is->audio_clock - last_clock,
               is->audio_clock, audio_clock0);
        last_clock = is->audio_clock;
    }
#endif
    return resampled_data_size;
}

/* prepare a new audio buffer */
static void sdl_audio_callback(void *opaque, Uint8 *stream, int len)
{
    VideoState *is = opaque;
    int audio_size, len1, vol;

    audio_callback_time = av_gettime_relative();

    while (len > 0) {
        if (is->audio_buf_index >= is->audio_buf_size) {
           audio_size = audio_decode_frame(is);
           if (audio_size < 0) {
                /* if error, just output silence */
               is->audio_buf = NULL;
               is->audio_buf_size = SDL_AUDIO_MIN_BUFFER_SIZE / is->audio_tgt.frame_size * is->audio_tgt.frame_size;
           } else {
               if (is->show_mode != SHOW_MODE_VIDEO)
                   update_sample_display(is, (int16_t *)is->audio_buf, audio_size);
               is->audio_buf_size = audio_size;
           }
           is->audio_buf_index = 0;
        }
        len1 = is->audio_buf_size - is->audio_buf_index;
        if (len1 > len)
            len1 = len;
        if (is->audio_buf && !is->paused) {         /* the loudness, for the cover art backdrop */
            const int16_t *sm = (const int16_t *)((uint8_t *)is->audio_buf + is->audio_buf_index);
            int cnt = len1 / 2, k, used = 0;
            double acc = 0;

            for (k = 0; k < cnt; k += 8, used++)
                acc += (double)sm[k] * sm[k];
            is->level = used ? (float)(sqrt(acc / used) / 32768.0) : 0.0f;
        } else {
            is->level = 0.0f;
        }
        {                                       /* quiet while seeking: the cut and restarted sound would scratch */
            static float duck = 1.0f;
            int64_t tnow = av_gettime_relative();
            float want = (is->seek_req || (is->prec_a && tnow - ui_seek_last < 1500000) || tnow - ui_seek_last < 260000) ? 0.0f : 1.0f;

            if (want < duck)
                duck = FFMAX(want, duck * 0.3f);        /* down within a few milliseconds */
            else
                duck = FFMIN(want, duck + 0.10f);       /* back up over about a third of a second */
            if (duck < 0.01f)
                duck = 0.0f;
            vol = (int)(is->audio_volume * is->xf_gain * ui_sleep_gain * duck + 0.5f);
        }
        if (!is->muted && is->audio_buf && vol == SDL_MIX_MAXVOLUME)
            memcpy(stream, (uint8_t *)is->audio_buf + is->audio_buf_index, len1);
        else {
            memset(stream, 0, len1);
            if (!is->muted && is->audio_buf)
                SDL_MixAudioFormat(stream, (uint8_t *)is->audio_buf + is->audio_buf_index, AUDIO_S16SYS, len1, vol);
        }
        len -= len1;
        stream += len1;
        is->audio_buf_index += len1;
    }
    is->audio_write_buf_size = is->audio_buf_size - is->audio_buf_index;
    /* Let's assume the audio driver that is used by SDL has two periods. */
    if (!isnan(is->audio_clock)) {
        set_clock_at(&is->audclk, is->audio_clock - (double)(2 * is->audio_hw_buf_size + is->audio_write_buf_size) / is->audio_tgt.bytes_per_sec, is->audio_clock_serial, audio_callback_time / 1000000.0);
        sync_clock_to_slave(&is->extclk, &is->audclk);
    }
}

static int audio_open(void *opaque, AVChannelLayout *wanted_channel_layout, int wanted_sample_rate, struct AudioParams *audio_hw_params)
{
    SDL_AudioSpec wanted_spec, spec;
    const char *env;
    static const int next_nb_channels[] = {0, 0, 1, 6, 2, 6, 4, 6};
    static const int next_sample_rates[] = {0, 44100, 48000, 96000, 192000};
    int next_sample_rate_idx = FF_ARRAY_ELEMS(next_sample_rates) - 1;
    int wanted_nb_channels = wanted_channel_layout->nb_channels;

    env = SDL_getenv("SDL_AUDIO_CHANNELS");
    if (env) {
        wanted_nb_channels = atoi(env);
        av_channel_layout_uninit(wanted_channel_layout);
        av_channel_layout_default(wanted_channel_layout, wanted_nb_channels);
    }
    if (wanted_channel_layout->order != AV_CHANNEL_ORDER_NATIVE) {
        av_channel_layout_uninit(wanted_channel_layout);
        av_channel_layout_default(wanted_channel_layout, wanted_nb_channels);
    }
    wanted_nb_channels = wanted_channel_layout->nb_channels;
    wanted_spec.channels = wanted_nb_channels;
    wanted_spec.freq = wanted_sample_rate;
    if (wanted_spec.freq <= 0 || wanted_spec.channels <= 0) {
        av_log(NULL, AV_LOG_ERROR, "Invalid sample rate or channel count!\n");
        return -1;
    }
    while (next_sample_rate_idx && next_sample_rates[next_sample_rate_idx] >= wanted_spec.freq)
        next_sample_rate_idx--;
    wanted_spec.format = AUDIO_S16SYS;
    wanted_spec.silence = 0;
    wanted_spec.samples = FFMAX(SDL_AUDIO_MIN_BUFFER_SIZE, 2 << av_log2(wanted_spec.freq / SDL_AUDIO_MAX_CALLBACKS_PER_SEC));
    wanted_spec.callback = sdl_audio_callback;
    wanted_spec.userdata = opaque;
    while (!(audio_dev = SDL_OpenAudioDevice(NULL, 0, &wanted_spec, &spec, SDL_AUDIO_ALLOW_FREQUENCY_CHANGE | SDL_AUDIO_ALLOW_CHANNELS_CHANGE))) {
        av_log(NULL, AV_LOG_WARNING, "SDL_OpenAudio (%d channels, %d Hz): %s\n",
               wanted_spec.channels, wanted_spec.freq, SDL_GetError());
        wanted_spec.channels = next_nb_channels[FFMIN(7, wanted_spec.channels)];
        if (!wanted_spec.channels) {
            wanted_spec.freq = next_sample_rates[next_sample_rate_idx--];
            wanted_spec.channels = wanted_nb_channels;
            if (!wanted_spec.freq) {
                av_log(NULL, AV_LOG_ERROR,
                       "No more combinations to try, audio open failed\n");
                return -1;
            }
        }
        av_channel_layout_default(wanted_channel_layout, wanted_spec.channels);
    }
    if (spec.format != AUDIO_S16SYS) {
        av_log(NULL, AV_LOG_ERROR,
               "SDL advised audio format %d is not supported!\n", spec.format);
        return -1;
    }
    if (spec.channels != wanted_spec.channels) {
        av_channel_layout_uninit(wanted_channel_layout);
        av_channel_layout_default(wanted_channel_layout, spec.channels);
        if (wanted_channel_layout->order != AV_CHANNEL_ORDER_NATIVE) {
            av_log(NULL, AV_LOG_ERROR,
                   "SDL advised channel count %d is not supported!\n", spec.channels);
            return -1;
        }
    }

    audio_hw_params->fmt = AV_SAMPLE_FMT_S16;
    audio_hw_params->freq = spec.freq;
    if (av_channel_layout_copy(&audio_hw_params->ch_layout, wanted_channel_layout) < 0)
        return -1;
    audio_hw_params->frame_size = av_samples_get_buffer_size(NULL, audio_hw_params->ch_layout.nb_channels, 1, audio_hw_params->fmt, 1);
    audio_hw_params->bytes_per_sec = av_samples_get_buffer_size(NULL, audio_hw_params->ch_layout.nb_channels, audio_hw_params->freq, audio_hw_params->fmt, 1);
    if (audio_hw_params->bytes_per_sec <= 0 || audio_hw_params->frame_size <= 0) {
        av_log(NULL, AV_LOG_ERROR, "av_samples_get_buffer_size failed\n");
        return -1;
    }
    return spec.size;
}

/* open a given stream. Return 0 if OK */
static int stream_component_open(VideoState *is, int stream_index)
{
    AVFormatContext *ic = is->ic;
    AVCodecContext *avctx;
    const AVCodec *codec;
    const char *forced_codec_name = NULL;
    AVDictionary *opts = NULL;
    const AVDictionaryEntry *t = NULL;
    int sample_rate;
    AVChannelLayout ch_layout = { 0 };
    int ret = 0;
    int stream_lowres = lowres;

    if (stream_index < 0 || stream_index >= ic->nb_streams)
        return -1;

    avctx = avcodec_alloc_context3(NULL);
    if (!avctx)
        return AVERROR(ENOMEM);

    ret = avcodec_parameters_to_context(avctx, ic->streams[stream_index]->codecpar);
    if (ret < 0)
        goto fail;
    avctx->pkt_timebase = ic->streams[stream_index]->time_base;

    codec = avcodec_find_decoder(avctx->codec_id);

    switch(avctx->codec_type){
        case AVMEDIA_TYPE_AUDIO   : is->last_audio_stream    = stream_index; forced_codec_name =    audio_codec_name; break;
        case AVMEDIA_TYPE_SUBTITLE: is->last_subtitle_stream = stream_index; forced_codec_name = subtitle_codec_name; break;
        case AVMEDIA_TYPE_VIDEO   : is->last_video_stream    = stream_index; forced_codec_name =    video_codec_name; break;
    }
    if (forced_codec_name)
        codec = avcodec_find_decoder_by_name(forced_codec_name);
    if (!codec) {
        if (forced_codec_name) av_log(NULL, AV_LOG_WARNING,
                                      "No codec could be found with name '%s'\n", forced_codec_name);
        else                   av_log(NULL, AV_LOG_WARNING,
                                      "No decoder could be found for codec %s\n", avcodec_get_name(avctx->codec_id));
        ret = AVERROR(EINVAL);
        goto fail;
    }

    avctx->codec_id = codec->id;
    if (stream_lowres > codec->max_lowres) {
        av_log(avctx, AV_LOG_WARNING, "The maximum value for lowres supported by the decoder is %d\n",
                codec->max_lowres);
        stream_lowres = codec->max_lowres;
    }
    avctx->lowres = stream_lowres;

    if (fast)
        avctx->flags2 |= AV_CODEC_FLAG2_FAST;

    ret = filter_codec_opts(codec_opts, avctx->codec_id, ic,
                            ic->streams[stream_index], codec, &opts);
    if (ret < 0)
        goto fail;

    if (!av_dict_get(opts, "threads", NULL, 0))
        av_dict_set(&opts, "threads", "auto", 0);
    if (stream_lowres)
        av_dict_set_int(&opts, "lowres", stream_lowres, 0);

    av_dict_set(&opts, "flags", "+copy_opaque", AV_DICT_MULTIKEY);

    if ((ret = avcodec_open2(avctx, codec, &opts)) < 0) {
        goto fail;
    }
    if ((t = av_dict_get(opts, "", NULL, AV_DICT_IGNORE_SUFFIX))) {
        av_log(NULL, AV_LOG_ERROR, "Option %s not found.\n", t->key);
        ret =  AVERROR_OPTION_NOT_FOUND;
        goto fail;
    }

    is->eof = 0;
    ic->streams[stream_index]->discard = AVDISCARD_DEFAULT;
    switch (avctx->codec_type) {
    case AVMEDIA_TYPE_AUDIO:
        {
            AVFilterContext *sink;

            is->audio_filter_src.freq           = avctx->sample_rate;
            ret = av_channel_layout_copy(&is->audio_filter_src.ch_layout, &avctx->ch_layout);
            if (ret < 0)
                goto fail;
            is->audio_filter_src.fmt            = avctx->sample_fmt;
            if ((ret = configure_audio_filters(is, afilters, 0)) < 0)
                goto fail;
            sink = is->out_audio_filter;
            sample_rate    = av_buffersink_get_sample_rate(sink);
            ret = av_buffersink_get_ch_layout(sink, &ch_layout);
            if (ret < 0)
                goto fail;
        }

        /* prepare audio output */
        if ((ret = audio_open(is, &ch_layout, sample_rate, &is->audio_tgt)) < 0)
            goto fail;
        is->audio_hw_buf_size = ret;
        is->audio_src = is->audio_tgt;
        is->audio_buf_size  = 0;
        is->audio_buf_index = 0;

        /* init averaging filter */
        is->audio_diff_avg_coef  = exp(log(0.01) / AUDIO_DIFF_AVG_NB);
        is->audio_diff_avg_count = 0;
        /* since we do not have a precise anough audio FIFO fullness,
           we correct audio sync only if larger than this threshold */
        is->audio_diff_threshold = (double)(is->audio_hw_buf_size) / is->audio_tgt.bytes_per_sec;

        is->audio_stream = stream_index;
        is->audio_st = ic->streams[stream_index];

        if ((ret = decoder_init(&is->auddec, avctx, &is->audioq, is->continue_read_thread)) < 0)
            goto fail;
        if (is->ic->iformat->flags & AVFMT_NOTIMESTAMPS) {
            is->auddec.start_pts = is->audio_st->start_time;
            is->auddec.start_pts_tb = is->audio_st->time_base;
        }
        if ((ret = decoder_start(&is->auddec, audio_thread, "audio_decoder", is)) < 0)
            goto out;
        is->audio_dev_id = audio_dev;
        SDL_PauseAudioDevice(is->audio_dev_id, 0);
        break;
    case AVMEDIA_TYPE_VIDEO:
        is->video_stream = stream_index;
        is->video_st = ic->streams[stream_index];

        if ((ret = decoder_init(&is->viddec, avctx, &is->videoq, is->continue_read_thread)) < 0)
            goto fail;
        if ((ret = decoder_start(&is->viddec, video_thread, "video_decoder", is)) < 0)
            goto out;
        is->queue_attachments_req = 1;
        break;
    case AVMEDIA_TYPE_SUBTITLE:
        is->subtitle_stream = stream_index;
        is->subtitle_st = ic->streams[stream_index];

        if ((ret = decoder_init(&is->subdec, avctx, &is->subtitleq, is->continue_read_thread)) < 0)
            goto fail;
        if ((ret = decoder_start(&is->subdec, subtitle_thread, "subtitle_decoder", is)) < 0)
            goto out;
        break;
    default:
        break;
    }
    goto out;

fail:
    avcodec_free_context(&avctx);
out:
    av_channel_layout_uninit(&ch_layout);
    av_dict_free(&opts);

    return ret;
}

static int decode_interrupt_cb(void *ctx)
{
    VideoState *is = ctx;
    return is->abort_request;
}

static int stream_has_enough_packets(AVStream *st, int stream_id, PacketQueue *queue) {
    return stream_id < 0 ||
           queue->abort_request ||
           (st->disposition & AV_DISPOSITION_ATTACHED_PIC) ||
           queue->nb_packets > MIN_FRAMES && (!queue->duration || av_q2d(st->time_base) * queue->duration > 1.0);
}

static int is_realtime(AVFormatContext *s)
{
    if(   !strcmp(s->iformat->name, "rtp")
       || !strcmp(s->iformat->name, "rtsp")
       || !strcmp(s->iformat->name, "sdp")
    )
        return 1;

    if(s->pb && (   !strncmp(s->url, "rtp:", 4)
                 || !strncmp(s->url, "udp:", 4)
                )
    )
        return 1;
    return 0;
}

/* this thread gets the stream from the disk or the network */
/* The end of the last video of the queue, when the player does not quit: it stays on its last picture instead */
static int ui_hold_last_wanted(VideoState *is)
{
    return !cfg_quit_when_done && is != xf_stream && is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) &&
           q_count > 0 && q_pos >= 0 && q_pos < q_count && q_forced < 0 && queue_next() >= q_count;
}

static int read_thread(void *arg)
{
    VideoState *is = arg;
    AVFormatContext *ic = NULL;
    int err, i, ret;
    int st_index[AVMEDIA_TYPE_NB];
    AVPacket *pkt = NULL;
    int64_t stream_start_time;
    int pkt_in_play_range = 0;
    const AVDictionaryEntry *t;
    SDL_mutex *wait_mutex = SDL_CreateMutex();
    int scan_all_pmts_set = 0;
    int64_t pkt_ts;

    if (!wait_mutex) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateMutex(): %s\n", SDL_GetError());
        ret = AVERROR(ENOMEM);
        goto fail;
    }

    memset(st_index, -1, sizeof(st_index));
    is->eof = 0;

    pkt = av_packet_alloc();
    if (!pkt) {
        av_log(NULL, AV_LOG_FATAL, "Could not allocate packet.\n");
        ret = AVERROR(ENOMEM);
        goto fail;
    }
    ic = avformat_alloc_context();
    if (!ic) {
        av_log(NULL, AV_LOG_FATAL, "Could not allocate context.\n");
        ret = AVERROR(ENOMEM);
        goto fail;
    }
    ic->interrupt_callback.callback = decode_interrupt_cb;
    ic->interrupt_callback.opaque = is;
    if (!av_dict_get(format_opts, "scan_all_pmts", NULL, AV_DICT_MATCH_CASE)) {
        av_dict_set(&format_opts, "scan_all_pmts", "1", AV_DICT_DONT_OVERWRITE);
        scan_all_pmts_set = 1;
    }
    err = avformat_open_input(&ic, is->filename, is->iformat, &format_opts);
    if (err < 0) {
        print_error(is->filename, err);
        ret = -1;
        goto fail;
    }
    if (scan_all_pmts_set)
        av_dict_set(&format_opts, "scan_all_pmts", NULL, AV_DICT_MATCH_CASE);

    if ((t = av_dict_get(format_opts, "", NULL, AV_DICT_IGNORE_SUFFIX))) {
        av_log(NULL, AV_LOG_ERROR, "Option %s not found.\n", t->key);
        ret = AVERROR_OPTION_NOT_FOUND;
        goto fail;
    }
    is->ic = ic;

    if (genpts)
        ic->flags |= AVFMT_FLAG_GENPTS;

    if (find_stream_info) {
        AVDictionary **opts;
        int orig_nb_streams = ic->nb_streams;

        err = setup_find_stream_info_opts(ic, codec_opts, &opts);
        if (err < 0) {
            av_log(NULL, AV_LOG_ERROR,
                   "Error setting up avformat_find_stream_info() options\n");
            ret = err;
            goto fail;
        }

        err = avformat_find_stream_info(ic, opts);

        for (i = 0; i < orig_nb_streams; i++)
            av_dict_free(&opts[i]);
        av_freep(&opts);

        if (err < 0) {
            av_log(NULL, AV_LOG_WARNING,
                   "%s: could not find codec parameters\n", is->filename);
            ret = -1;
            goto fail;
        }
    }

    if (ic->pb)
        ic->pb->eof_reached = 0; // FIXME hack, ffplay maybe should not use avio_feof() to test for the end

    if (seek_by_bytes < 0)
        seek_by_bytes = !(ic->iformat->flags & AVFMT_NO_BYTE_SEEK) &&
                        !!(ic->iformat->flags & AVFMT_TS_DISCONT) &&
                        strcmp("ogg", ic->iformat->name);

    is->max_frame_duration = (ic->iformat->flags & AVFMT_TS_DISCONT) ? 10.0 : 3600.0;

    if (!window_title && (t = av_dict_get(ic->metadata, "title", NULL, 0)))
        window_title = av_asprintf("%s - %s", t->value, input_filename);

    /* if seeking requested, we execute it */
    if (start_time != AV_NOPTS_VALUE) {
        int64_t timestamp;

        timestamp = start_time;
        /* add the stream start time */
        if (ic->start_time != AV_NOPTS_VALUE)
            timestamp += ic->start_time;
        ret = avformat_seek_file(ic, -1, INT64_MIN, timestamp, INT64_MAX, 0);
        if (ret < 0) {
            av_log(NULL, AV_LOG_WARNING, "%s: could not seek to position %0.3f\n",
                    is->filename, (double)timestamp / AV_TIME_BASE);
        }
    }

    is->realtime = is_realtime(ic);

    if (show_status)
        av_dump_format(ic, 0, is->filename, 0);

    for (i = 0; i < ic->nb_streams; i++) {
        AVStream *st = ic->streams[i];
        enum AVMediaType type = st->codecpar->codec_type;
        st->discard = AVDISCARD_ALL;
        if (type >= 0 && wanted_stream_spec[type] && st_index[type] == -1)
            if (avformat_match_stream_specifier(ic, st, wanted_stream_spec[type]) > 0)
                st_index[type] = i;
    }
    for (i = 0; i < AVMEDIA_TYPE_NB; i++) {
        if (wanted_stream_spec[i] && st_index[i] == -1) {
            av_log(NULL, AV_LOG_ERROR, "Stream specifier %s does not match any %s stream\n", wanted_stream_spec[i], av_get_media_type_string(i));
            st_index[i] = INT_MAX;
        }
    }

    if (!video_disable)
        st_index[AVMEDIA_TYPE_VIDEO] =
            av_find_best_stream(ic, AVMEDIA_TYPE_VIDEO,
                                st_index[AVMEDIA_TYPE_VIDEO], -1, NULL, 0);
    if (!audio_disable)
        st_index[AVMEDIA_TYPE_AUDIO] =
            av_find_best_stream(ic, AVMEDIA_TYPE_AUDIO,
                                st_index[AVMEDIA_TYPE_AUDIO],
                                st_index[AVMEDIA_TYPE_VIDEO],
                                NULL, 0);
    if (!video_disable && !subtitle_disable)
        st_index[AVMEDIA_TYPE_SUBTITLE] =
            av_find_best_stream(ic, AVMEDIA_TYPE_SUBTITLE,
                                st_index[AVMEDIA_TYPE_SUBTITLE],
                                (st_index[AVMEDIA_TYPE_AUDIO] >= 0 ?
                                 st_index[AVMEDIA_TYPE_AUDIO] :
                                 st_index[AVMEDIA_TYPE_VIDEO]),
                                NULL, 0);

    is->show_mode = show_mode;
    if (st_index[AVMEDIA_TYPE_VIDEO] >= 0) {
        AVStream *st = ic->streams[st_index[AVMEDIA_TYPE_VIDEO]];
        AVCodecParameters *codecpar = st->codecpar;
        AVRational sar = av_guess_sample_aspect_ratio(ic, st, NULL);
        if (codecpar->width)
            set_default_window_size(codecpar->width, codecpar->height, sar);
    }

    /* open the streams */
    if (st_index[AVMEDIA_TYPE_AUDIO] >= 0) {
        stream_component_open(is, st_index[AVMEDIA_TYPE_AUDIO]);
    }

    ret = -1;
    if (st_index[AVMEDIA_TYPE_VIDEO] >= 0) {
        ret = stream_component_open(is, st_index[AVMEDIA_TYPE_VIDEO]);
    }
    if (is->show_mode == SHOW_MODE_NONE)
        is->show_mode = ret >= 0 ? SHOW_MODE_VIDEO : SHOW_MODE_RDFT;

    if (st_index[AVMEDIA_TYPE_SUBTITLE] >= 0) {
        stream_component_open(is, st_index[AVMEDIA_TYPE_SUBTITLE]);
    }

    if (is->video_stream < 0 && is->audio_stream < 0) {
        av_log(NULL, AV_LOG_FATAL, "Failed to open file '%s' or configure filtergraph\n",
               is->filename);
        ret = -1;
        goto fail;
    }

    if (infinite_buffer < 0 && is->realtime)
        infinite_buffer = 1;

    for (;;) {
        if (is->abort_request)
            break;
        if (is->paused != is->last_paused) {
            is->last_paused = is->paused;
            if (is->paused)
                is->read_pause_return = av_read_pause(ic);
            else
                av_read_play(ic);
        }
#if CONFIG_RTSP_DEMUXER || CONFIG_MMSH_PROTOCOL
        if (is->paused &&
                (!strcmp(ic->iformat->name, "rtsp") ||
                 (ic->pb && !strncmp(input_filename, "mmsh:", 5)))) {
            /* wait 10 ms to avoid trying to get another packet */
            /* XXX: horrible */
            SDL_Delay(10);
            continue;
        }
#endif
        if (is->seek_req) {
            int64_t seek_target = is->seek_pos;
            int64_t seek_min    = is->seek_rel > 0 ? seek_target - is->seek_rel + 2: INT64_MIN;
            int64_t seek_max    = is->seek_rel < 0 ? seek_target - is->seek_rel - 2: INT64_MAX;
            if (is->seek_precise && !(is->seek_flags & AVSEEK_FLAG_BYTE)) {
                seek_min = INT64_MIN;           /* exact landing: start at the key frame before the time, */
                seek_max = seek_target;         /* the pictures and sound before it are skipped */
            }
// FIXME the +-2 is due to rounding being not done in the correct direction in generation
//      of the seek_pos/seek_rel variables

            ret = avformat_seek_file(is->ic, -1, seek_min, seek_target, seek_max, is->seek_flags);
            if (ret < 0) {
                av_log(NULL, AV_LOG_ERROR,
                       "%s: error while seeking\n", is->ic->url);
            } else {
                if (is->audio_stream >= 0)
                    packet_queue_flush(&is->audioq);
                if (is->subtitle_stream >= 0)
                    packet_queue_flush(&is->subtitleq);
                if (is->video_stream >= 0)
                    packet_queue_flush(&is->videoq);
                if (is->seek_flags & AVSEEK_FLAG_BYTE) {
                   set_clock(&is->extclk, NAN, 0);
                } else {
                   set_clock(&is->extclk, seek_target / (double)AV_TIME_BASE, 0);
                }
                is->prec_v = is->prec_a = 0;
                if (is->seek_precise && !(is->seek_flags & AVSEEK_FLAG_BYTE)) {
                    is->prec_target = seek_target / (double)AV_TIME_BASE;
                    if (is->video_stream >= 0 && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
                        is->prec_ser_v = is->videoq.serial;
                        is->prec_v = 1;
                    }
                    if (is->audio_stream >= 0) {
                        is->prec_ser_a = is->audioq.serial;
                        is->prec_a = 1;
                    }
                }

            }
            is->seek_req = 0;
            is->queue_attachments_req = 1;
            is->eof = 0;
            if (is->paused)
                step_to_next_frame(is);
        }
        if (is->queue_attachments_req) {
            if (is->video_st && is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) {
                if ((ret = av_packet_ref(pkt, &is->video_st->attached_pic)) < 0)
                    goto fail;
                packet_queue_put(&is->videoq, pkt);
                packet_queue_put_nullpacket(&is->videoq, pkt, is->video_stream);
            }
            is->queue_attachments_req = 0;
        }

        /* if the queue are full, no need to read more */
        if (infinite_buffer<1 &&
              (is->audioq.size + is->videoq.size + is->subtitleq.size > MAX_QUEUE_SIZE
            || (stream_has_enough_packets(is->audio_st, is->audio_stream, &is->audioq) &&
                stream_has_enough_packets(is->video_st, is->video_stream, &is->videoq) &&
                stream_has_enough_packets(is->subtitle_st, is->subtitle_stream, &is->subtitleq)))) {
            /* wait 10 ms */
            SDL_LockMutex(wait_mutex);
            SDL_CondWaitTimeout(is->continue_read_thread, wait_mutex, 10);
            SDL_UnlockMutex(wait_mutex);
            continue;
        }
        if (!is->paused &&
            (!is->audio_st || (is->auddec.finished == is->audioq.serial && frame_queue_nb_remaining(&is->sampq) == 0)) &&
            (!is->video_st || (is->viddec.finished == is->videoq.serial && frame_queue_nb_remaining(&is->pictq) == 0))) {
            if (loop != 1 && (!loop || --loop)) {
                stream_seek(is, start_time != AV_NOPTS_VALUE ? start_time : 0, 0, 0);
            } else if (autoexit) {
                if (ui_hold_last_wanted(is)) {
                    if (!is->ui_held)
                        is->ui_hold = 1;        /* the main loop pauses on the last picture */
                } else {
                    ret = AVERROR_EOF;
                    goto fail;
                }
            }
        }
        ret = av_read_frame(ic, pkt);
        if (ret < 0) {
            if ((ret == AVERROR_EOF || avio_feof(ic->pb)) && !is->eof) {
                if (is->video_stream >= 0)
                    packet_queue_put_nullpacket(&is->videoq, pkt, is->video_stream);
                if (is->audio_stream >= 0)
                    packet_queue_put_nullpacket(&is->audioq, pkt, is->audio_stream);
                if (is->subtitle_stream >= 0)
                    packet_queue_put_nullpacket(&is->subtitleq, pkt, is->subtitle_stream);
                is->eof = 1;
            }
            if (ic->pb && ic->pb->error) {
                if (autoexit)
                    goto fail;
                else
                    break;
            }
            SDL_LockMutex(wait_mutex);
            SDL_CondWaitTimeout(is->continue_read_thread, wait_mutex, 10);
            SDL_UnlockMutex(wait_mutex);
            continue;
        } else {
            is->eof = 0;
        }
        /* check if packet is in play range specified by user, then queue, otherwise discard */
        stream_start_time = ic->streams[pkt->stream_index]->start_time;
        pkt_ts = pkt->pts == AV_NOPTS_VALUE ? pkt->dts : pkt->pts;
        pkt_in_play_range = duration == AV_NOPTS_VALUE ||
                (pkt_ts - (stream_start_time != AV_NOPTS_VALUE ? stream_start_time : 0)) *
                av_q2d(ic->streams[pkt->stream_index]->time_base) -
                (double)(start_time != AV_NOPTS_VALUE ? start_time : 0) / 1000000
                <= ((double)duration / 1000000);
        if (pkt->stream_index == is->audio_stream && pkt_in_play_range) {
            packet_queue_put(&is->audioq, pkt);
        } else if (pkt->stream_index == is->video_stream && pkt_in_play_range
                   && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
            packet_queue_put(&is->videoq, pkt);
        } else if (pkt->stream_index == is->subtitle_stream && pkt_in_play_range) {
            packet_queue_put(&is->subtitleq, pkt);
        } else {
            av_packet_unref(pkt);
        }
    }

    ret = 0;
 fail:
    if (ic && !is->ic)
        avformat_close_input(&ic);

    av_packet_free(&pkt);
    if (ret != 0) {
        SDL_Event event;

        event.type = FF_QUIT_EVENT;
        event.user.data1 = is;
        SDL_PushEvent(&event);
    }
    SDL_DestroyMutex(wait_mutex);
    return 0;
}

static VideoState *stream_open(const char *filename,
                               const AVInputFormat *iformat)
{
    VideoState *is;

    is = av_mallocz(sizeof(VideoState));
    if (!is)
        return NULL;
    is->last_video_stream = is->video_stream = -1;
    is->last_audio_stream = is->audio_stream = -1;
    is->last_subtitle_stream = is->subtitle_stream = -1;
    is->filename = av_strdup(filename);
    if (!is->filename)
        goto fail;
    is->iformat = iformat;
    is->ytop    = 0;
    is->xleft   = 0;

    /* start video display */
    if (frame_queue_init(&is->pictq, &is->videoq, VIDEO_PICTURE_QUEUE_SIZE, 1) < 0)
        goto fail;
    if (frame_queue_init(&is->subpq, &is->subtitleq, SUBPICTURE_QUEUE_SIZE, 0) < 0)
        goto fail;
    if (frame_queue_init(&is->sampq, &is->audioq, SAMPLE_QUEUE_SIZE, 1) < 0)
        goto fail;

    if (packet_queue_init(&is->videoq) < 0 ||
        packet_queue_init(&is->audioq) < 0 ||
        packet_queue_init(&is->subtitleq) < 0)
        goto fail;

    if (!(is->continue_read_thread = SDL_CreateCond())) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateCond(): %s\n", SDL_GetError());
        goto fail;
    }

    init_clock(&is->vidclk, &is->videoq.serial);
    init_clock(&is->audclk, &is->audioq.serial);
    init_clock(&is->extclk, &is->extclk.serial);
    is->audio_clock_serial = -1;
    if (startup_volume < 0)
        av_log(NULL, AV_LOG_WARNING, "-volume=%d < 0, setting to 0\n", startup_volume);
    if (startup_volume > 100)
        av_log(NULL, AV_LOG_WARNING, "-volume=%d > 100, setting to 100\n", startup_volume);
    startup_volume = av_clip(startup_volume, 0, 100);
    startup_volume = av_clip(SDL_MIX_MAXVOLUME * startup_volume / 100, 0, SDL_MIX_MAXVOLUME);
    is->audio_volume = volume_load(startup_volume);
    is->muted = 0;
    is->xf_gain = xf_open_gain;
    is->stream_id = ++ui_stream_serial;
    is->av_sync_type = av_sync_type;
    is->read_tid     = SDL_CreateThread(read_thread, "read_thread", is);
    if (!is->read_tid) {
        av_log(NULL, AV_LOG_FATAL, "SDL_CreateThread(): %s\n", SDL_GetError());
fail:
        stream_close(is);
        return NULL;
    }
    return is;
}

static void stream_cycle_channel(VideoState *is, int codec_type)
{
    AVFormatContext *ic = is->ic;
    int start_index, stream_index;
    int old_index;
    AVStream *st;
    AVProgram *p = NULL;
    int nb_streams = is->ic->nb_streams;

    if (codec_type == AVMEDIA_TYPE_VIDEO) {
        start_index = is->last_video_stream;
        old_index = is->video_stream;
    } else if (codec_type == AVMEDIA_TYPE_AUDIO) {
        start_index = is->last_audio_stream;
        old_index = is->audio_stream;
    } else {
        start_index = is->last_subtitle_stream;
        old_index = is->subtitle_stream;
    }
    stream_index = start_index;

    if (codec_type != AVMEDIA_TYPE_VIDEO && is->video_stream != -1) {
        p = av_find_program_from_stream(ic, NULL, is->video_stream);
        if (p) {
            nb_streams = p->nb_stream_indexes;
            for (start_index = 0; start_index < nb_streams; start_index++)
                if (p->stream_index[start_index] == stream_index)
                    break;
            if (start_index == nb_streams)
                start_index = -1;
            stream_index = start_index;
        }
    }

    for (;;) {
        if (++stream_index >= nb_streams)
        {
            if (codec_type == AVMEDIA_TYPE_SUBTITLE)
            {
                stream_index = -1;
                is->last_subtitle_stream = -1;
                goto the_end;
            }
            if (start_index == -1)
                return;
            stream_index = 0;
        }
        if (stream_index == start_index)
            return;
        st = is->ic->streams[p ? p->stream_index[stream_index] : stream_index];
        if (st->codecpar->codec_type == codec_type) {
            /* check that parameters are OK */
            switch (codec_type) {
            case AVMEDIA_TYPE_AUDIO:
                if (st->codecpar->sample_rate != 0 &&
                    st->codecpar->ch_layout.nb_channels != 0)
                    goto the_end;
                break;
            case AVMEDIA_TYPE_VIDEO:
            case AVMEDIA_TYPE_SUBTITLE:
                goto the_end;
            default:
                break;
            }
        }
    }
 the_end:
    if (p && stream_index != -1)
        stream_index = p->stream_index[stream_index];
    av_log(NULL, AV_LOG_INFO, "Switch %s stream from #%d to #%d\n",
           av_get_media_type_string(codec_type),
           old_index,
           stream_index);

    stream_component_close(is, old_index);
    stream_component_open(is, stream_index);
}


static void toggle_full_screen(VideoState *is)
{
    is_full_screen = !is_full_screen;
    ui_fs_toggle_at = av_gettime_relative();
    ui_prog_until = av_gettime_relative() + 2000000;     /* the size changes of going in and out are ours */
    SDL_SetWindowFullscreen(window, is_full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
}

static void toggle_audio_display(VideoState *is)
{
    int next = is->show_mode;
    do {
        next = (next + 1) % SHOW_MODE_NB;
    } while (next != is->show_mode && (next == SHOW_MODE_VIDEO && !is->video_st || next != SHOW_MODE_VIDEO && !is->audio_st));
    if (is->show_mode != next) {
        is->force_refresh = 1;
        is->show_mode = next;
    }
}

static int64_t ui_aspect_due = 0;   /* when to snap the window, 0 = not pending */
static void ui_aspect_tick(VideoState *is);

/* ----- the sleep timer and the crossfade: both are checked on every turn of the event loop ----- */

/* Close the next item if it was started early */
static double ui_xf_t = 0.0;            /* 0 to 1: how far the crossfade has gone */

/* The picture of the next video, drawn over the end of this one, a little stronger each moment */
static void ui_xf_video_draw(VideoState *is, int to_tile)
{
    VideoState *xf = xf_stream;
    Frame *np;
    SDL_Rect r;

    if (!xf || ui_xf_t <= 0.0 || !xf->video_st || (xf->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC) ||
        xf->pictq.size <= 0 || (!to_tile && (ui_flow_video(is) || ui_has_cover(is))))
        return;
    np = frame_queue_peek_last(&xf->pictq);
    if (!np->frame || !np->frame->width || !np->width || !np->height)
        return;
    if (to_tile)                                /* drawn into the picture of the tile: its whole area */
        calculate_display_rect(&r, 0, 0, ui_live_w, ui_live_h, np->width, np->height, np->sar);
    else
        calculate_display_rect(&r, is->xleft, is->ytop, is->width, is->height, np->width, np->height, np->sar);
    set_sdl_yuv_conversion_mode(np->frame);
    if (!np->uploaded) {
        if (upload_texture(&xf->vid_texture, np->frame) < 0) {
            set_sdl_yuv_conversion_mode(NULL);
            return;
        }
        np->uploaded = 1;
        np->flip_v = np->frame->linesize[0] < 0;
    }
    SDL_SetTextureBlendMode(xf->vid_texture, SDL_BLENDMODE_BLEND);
    SDL_SetTextureAlphaMod(xf->vid_texture, (Uint8)(255.0 * av_clipd(ui_xf_t, 0.0, 1.0)));
    SDL_RenderCopyEx(renderer, xf->vid_texture, NULL, &r, 0, NULL, np->flip_v ? SDL_FLIP_VERTICAL : 0);
    SDL_SetTextureAlphaMod(xf->vid_texture, 255);
    set_sdl_yuv_conversion_mode(NULL);
}

static void ui_xf_abort(void)
{
    ui_xf_t = 0.0;
    if (xf_stream) {
        stream_close(xf_stream);
        xf_stream = NULL;
    }
    xf_name = NULL;
}

/* A timed sleep: the sound fades out over the last 20 seconds, then playback pauses.
   is = the stream playing now, or NULL on the idle screen. */
static void ui_sleep_tick(VideoState *is)
{
    int64_t left;
    double pos, dur;

    /* "End of track" / "Sleep after this item": pause a moment before the item ends, and stay where we are.
       The queue view and the queue stay as they are; play carries on into the last moments and then the next item. */
    if (is && q_sleep_item && q_pos >= 0 && q_pos < q_count && q_sleep_item == q_items[q_pos] && !is->paused &&
        is->ic && is->ic->duration > 0) {
        pos = get_master_clock(is);
        if (!isnan(pos)) {
            if (is->ic->start_time != AV_NOPTS_VALUE)
                pos -= is->ic->start_time / (double)AV_TIME_BASE;
            dur = is->ic->duration / (double)AV_TIME_BASE;
            if (dur - pos < 0.35 && dur - pos > -5.0) {
                q_sleep_item = NULL;
                ui_sleep_sel = 0;
                ui_xf_abort();
                is->xf_gain = 1.0f;
                toggle_pause(is);
                is->force_refresh = 1;
            }
        }
    }
    if (!q_sleep_end)
        return;
    left = q_sleep_end - av_gettime_relative();
    if (left <= 0) {
        q_sleep_end = 0;
        ui_sleep_sel = 0;
        ui_sleep_gain = 1.0f;
        ui_xf_abort();
        if (is) {
            is->xf_gain = 1.0f;
            if (!is->paused)
                toggle_pause(is);
            is->force_refresh = 1;
        }
        return;
    }
    ui_sleep_gain = left < 20000000 ? (float)(left / 20000000.0) : 1.0f;
}

/* The crossfade. Shortly before an item ends, the next one is opened as a second stream and starts
   playing quietly. The old one fades out while the new one fades in; when the old one ends, the new
   one simply becomes the stream that is playing (see the main loop). */
static void ui_xfade_tick(VideoState *is)
{
    VideoState *xf = xf_stream;
    double dur, pos, rem, t, c;
    int n = cfg_crossfade, next;

    if (!is || !is->ic || !is->audio_st || q_pos < 0 || q_pos >= q_count)
        return;
    pos = get_master_clock(is);
    if (isnan(pos))
        return;
    if (is->ic->start_time != AV_NOPTS_VALUE)
        pos -= is->ic->start_time / (double)AV_TIME_BASE;
    dur = is->ic->duration > 0 ? is->ic->duration / (double)AV_TIME_BASE : 0;
    rem = dur - pos;
    next = queue_next();

    if (xf) {
        if (n <= 0 || dur <= 0 || next >= q_count || xf_name != q_items[next] || rem > n + 1.0 ||
            (q_sleep_item && q_sleep_item == q_items[q_pos])) {
            is->xf_gain = 1.0f;         /* the plan changed (a seek, a click, the setting): back to normal */
            ui_xf_abort();
            return;
        }
        t = av_clipd(1.0 - rem / n, 0.0, 1.0);
        is->xf_gain = (float)cos(t * M_PI / 2);     /* equal power: the total loudness stays level */
        xf->xf_gain = (float)sin(t * M_PI / 2);
        ui_xf_t = t;                            /* the picture fades in the same way */
        xf->audio_volume = is->audio_volume;
        xf->muted = is->muted;
        if (xf->paused != is->paused)
            stream_toggle_pause(xf);
        c = get_master_clock(xf);               /* nothing shows its pictures yet: drop the old ones */
        if (!isnan(c))
            while (frame_queue_nb_remaining(&xf->pictq) > 1) {
                Frame *nx = frame_queue_peek_next(&xf->pictq);

                if (isnan(nx->pts) || nx->pts >= c)
                    break;
                frame_queue_next(&xf->pictq);
            }
        return;
    }

    if (n <= 0 || is->paused || dur < 2.0 * n + 2.0 || rem > n || rem < 0.3 || q_forced >= 0 || q_step != 1 || q_repeat == 2 ||
        next >= q_count || next == q_pos || q_hold || ui_seek_want || q_items[next] == xf_failed ||
        (q_sleep_item && q_sleep_item == q_items[q_pos]))
        return;
    if (!window_title)
        window_title = input_filename;          /* so opening the next item leaves the window title alone */
    startup_volume = 100;
    xf_open_gain = 0.0f;                        /* silent from the first moment */
    xf = stream_open(q_items[next], file_iformat);
    xf_open_gain = 1.0f;
    if (!xf) {
        xf_failed = q_items[next];
        return;
    }
    xf->audio_volume = is->audio_volume;
    xf->muted = is->muted;
    ui_xf_t = 0.0;
    xf_stream = xf;
    xf_name = q_items[next];
}

/* ----- the desktop's media controls (MPRIS) -----
   ffplay-custom starts a small helper, "ffplay-mpris", which shows up on the desktop as a media player: the sound
   indicator in the top panel, the media keys and playerctl then control playback. We tell the helper what is
   playing through its stdin; it hands commands back through a file, which is read a few times a second. */
#include <stdarg.h>

static FILE *mpris_out = NULL;              /* the helper's stdin */
static int mpris_started = 0;
static char mpris_cmd_path[PATH_MAX] = "";  /* the file the helper writes commands to */
static int64_t mpris_poll_at = 0;

static void ui_mpris_put(const char *fmt, ...)
{
    va_list ap;

    if (!mpris_out)
        return;
    va_start(ap, fmt);
    if (vfprintf(mpris_out, fmt, ap) < 0 || fflush(mpris_out) != 0) {
        fclose(mpris_out);                  /* the helper is gone */
        mpris_out = NULL;
    }
    va_end(ap);
}

static void ui_mpris_start(void)
{
    const char *home = getenv("HOME");
    char dir[PATH_MAX - 16];
    int fds[2], i;
    pid_t pid;

    if (!home)
        return;
    snprintf(dir, sizeof(dir), "%s/.cache", home);
    mkdir(dir, 0755);
    snprintf(dir, sizeof(dir), "%s/.cache/ffplay-custom", home);
    mkdir(dir, 0755);
    snprintf(mpris_cmd_path, sizeof(mpris_cmd_path), "%s/mpris.cmd", dir);
    unlink(mpris_cmd_path);
    if (pipe(fds) != 0)
        return;
    pid = fork();
    if (pid < 0) {
        close(fds[0]);
        close(fds[1]);
        return;
    }
    if (pid == 0) {                         /* the helper: stdin is our pipe, everything else is closed */
        dup2(fds[0], 0);
        for (i = 3; i < 256; i++)
            close(i);
        execlp("ffplay-mpris", "ffplay-mpris", mpris_cmd_path, (char *)NULL);
        _exit(127);
    }
    close(fds[0]);
    signal(SIGPIPE, SIG_IGN);
    mpris_out = fdopen(fds[1], "w");
}

static void ui_mpris_clean(char *s)
{
    for (; *s; s++)
        if (*s == '\t' || *s == '\n' || *s == '\r')
            *s = ' ';
}

/* Where the playing position is, in seconds from the start of the file */
static double ui_mpris_pos(VideoState *is)
{
    double c = get_master_clock(is);

    if (isnan(c))
        return 0;
    if (is->ic && is->ic->start_time != AV_NOPTS_VALUE)
        c -= is->ic->start_time / (double)AV_TIME_BASE;
    return FFMAX(c, 0.0);
}

static void ui_mpris_seek_to(VideoState *is, double secs)
{
    int64_t ts;

    if (!is || !is->ic || is->ic->duration <= 0 || is->seek_req)
        return;
    secs = av_clipd(secs, 0.0, FFMAX(is->ic->duration / (double)AV_TIME_BASE - 0.5, 0.0));
    ts = (int64_t)(secs * AV_TIME_BASE);
    if (is->ic->start_time != AV_NOPTS_VALUE)
        ts += is->ic->start_time;
    stream_seek(is, ts, 0, 0);
}

/* Tell the helper what is playing: title, artist, album, length and the cover art (saved as a file) */
static void ui_mpris_meta(VideoState *is, int track)
{
    static int art_n = 0;
    char title[300] = "", artist[200] = "", album[200] = "", art[PATH_MAX + 16] = "", file[PATH_MAX], *dot;
    const char *home = getenv("HOME"), *base;
    AVDictionaryEntry *e;
    unsigned i;
    int64_t dur_us = 0;

    if (is->ic) {
        if ((e = av_dict_get(is->ic->metadata, "title", NULL, 0)))
            snprintf(title, sizeof(title), "%s", e->value);
        if ((e = av_dict_get(is->ic->metadata, "artist", NULL, 0)))
            snprintf(artist, sizeof(artist), "%s", e->value);
        if ((e = av_dict_get(is->ic->metadata, "album", NULL, 0)))
            snprintf(album, sizeof(album), "%s", e->value);
        if (is->ic->duration > 0)
            dur_us = is->ic->duration;
    }
    if (!title[0]) {                        /* no title tag: the file name without its ending */
        base = strrchr(is->filename, '/');
        snprintf(title, sizeof(title), "%s", base ? base + 1 : is->filename);
        dot = strrchr(title, '.');
        if (dot && dot != title)
            *dot = 0;
    }
    if (home && is->ic) {
        for (i = 0; i < is->ic->nb_streams; i++) {
            AVStream *st = is->ic->streams[i];

            if ((st->disposition & AV_DISPOSITION_ATTACHED_PIC) && st->attached_pic.size > 0) {
                FILE *f;

                snprintf(file, sizeof(file), "%s/.cache/ffplay-custom/cover-%d.%s", home, art_n++ % 4,
                         st->codecpar->codec_id == AV_CODEC_ID_PNG ? "png" : "jpg");
                f = fopen(file, "wb");
                if (f) {
                    fwrite(st->attached_pic.data, 1, st->attached_pic.size, f);
                    fclose(f);
                    snprintf(art, sizeof(art), "file://%s", file);
                }
                break;
            }
        }
    }
    ui_mpris_clean(title);
    ui_mpris_clean(artist);
    ui_mpris_clean(album);
    ui_mpris_put("meta\t%s\t%s\t%s\t%lld\t%s\t%d\n", title, artist, album, (long long)dur_us, art, track);
}

/* Play from the idle screen: the queue from the top, or on after a sleep stop */
static void ui_idle_play(void)
{
    if (q_count > 0)
        q_forced = (q_hold && q_pos + 1 < q_count) ? q_pos + 1 : 0;
}

static void ui_mpris_command(VideoState *is, const char *line)
{
    long long n;
    double f;

    if (!strcmp(line, "playpause")) {
        if (is)
            toggle_pause(is);
        else
            ui_idle_play();
    } else if (!strcmp(line, "play")) {
        if (!is)
            ui_idle_play();
        else if (is->paused)
            toggle_pause(is);
    } else if (!strcmp(line, "pause")) {
        if (is && !is->paused)
            toggle_pause(is);
    } else if (!strcmp(line, "stop")) {
        if (is) {
            q_hold = 1;                     /* back to the idle screen; play carries on with the next item */
            ui_end_current(is);
        }
    } else if (!strcmp(line, "next")) {
        q_step = 1;
        if (is)
            ui_end_current(is);
        else if (q_count > 0)
            q_forced = av_clip(q_pos + 1, 0, q_count - 1);
    } else if (!strcmp(line, "prev")) {
        if (is && ui_mpris_pos(is) > 3.0) {
            ui_mpris_seek_to(is, 0.0);      /* a few seconds in: back to the start of this item first */
        } else {
            q_step = -1;
            if (is)
                ui_end_current(is);
            else if (q_count > 0)
                q_forced = av_clip(q_pos - 1, 0, q_count - 1);
        }
    } else if (sscanf(line, "seek %lld", &n) == 1) {
        if (is)
            ui_mpris_seek_to(is, ui_mpris_pos(is) + n / 1e6);
    } else if (sscanf(line, "setpos %lld", &n) == 1) {
        if (is)
            ui_mpris_seek_to(is, n / 1e6);
    } else if (sscanf(line, "vol %lf", &f) == 1) {
        if (is) {
            is->audio_volume = av_clip((int)(f * SDL_MIX_MAXVOLUME + 0.5), 0, SDL_MIX_MAXVOLUME);
            is->muted = 0;
        }
    } else if (sscanf(line, "shuffle %lld", &n) == 1) {
        queue_set_shuffle(n != 0);
    } else if (!strcmp(line, "raise")) {
        SDL_RaiseWindow(window);
    } else if (!strcmp(line, "quit")) {
        do_exit(is);
    }
}

/* Read what the helper has been asked to do since the last look */
static void ui_mpris_commands(VideoState *is)
{
    char work[PATH_MAX + 8], line[256];
    FILE *f;

    snprintf(work, sizeof(work), "%s.work", mpris_cmd_path);
    if (rename(mpris_cmd_path, work) != 0)
        return;                             /* nothing was asked */
    f = fopen(work, "r");
    if (!f)
        return;
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\r\n")] = 0;
        if (line[0])
            ui_mpris_command(is, line);
    }
    fclose(f);
    unlink(work);
}

/* On every turn of the loop: start the helper once, pass on its commands, tell it what changed.
   is = the stream playing now, or NULL on the idle screen. */
static void ui_mpris_tick(VideoState *is)
{
    static unsigned last_id = 0;
    static char last_status[12] = "";
    static int last_shuffle = -1, last_vol = -1, last_can = -1, track = 0;
    static int64_t next_pos = 0;
    const char *status;
    int64_t now = av_gettime_relative();
    int vol, can;

    if (!mpris_started) {
        mpris_started = 1;
        ui_mpris_start();
    }
    if (!mpris_out)
        return;
    if (now >= mpris_poll_at) {
        mpris_poll_at = now + 150000;
        ui_mpris_commands(is);
        if (!mpris_out)
            return;
    }
    if (is && !is->audio_st && !is->video_st)
        return;                             /* still opening: keep saying what it said */
    if ((is ? is->stream_id : 0) != last_id) {         /* a different stream (not just the same address again) */
        last_id = is ? is->stream_id : 0;
        last_status[0] = 0;
        next_pos = 0;
        if (is)
            ui_mpris_meta(is, ++track);
    }
    if (is && now >= next_pos) {
        next_pos = now + 1000000;
        ui_mpris_put("pos\t%lld\n", (long long)(ui_mpris_pos(is) * 1e6));
    }
    status = !is ? "Stopped" : is->paused ? "Paused" : "Playing";
    if (strcmp(status, last_status)) {
        snprintf(last_status, sizeof(last_status), "%s", status);
        ui_mpris_put("status\t%s\n", status);
    }
    vol = is ? is->audio_volume : -1;
    if (vol != last_vol) {
        last_vol = vol;
        if (vol >= 0)
            ui_mpris_put("vol\t%.3f\n", vol / (double)SDL_MIX_MAXVOLUME);
    }
    if (q_shuffle != last_shuffle) {
        last_shuffle = q_shuffle;
        ui_mpris_put("shuffle\t%d\n", q_shuffle ? 1 : 0);
    }
    can = q_count > 0;
    if (can != last_can) {
        last_can = can;
        ui_mpris_put("can\t%d\t%d\n", can, can);
    }
}

/* A pause opens the queue view over a video that is part of a queue; playing again closes it. The last picture of the
   last video stays on screen, paused, when the queue ends and the player does not quit. */
static void ui_pause_tick(VideoState *is)
{
    static int seen = 0;
    static int64_t unpaused_at = 0;
    int vid = is->video_st && !(is->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC);
    int64_t now = av_gettime_relative();

    if (ui_tile_fs_pending) {
        if (ui_vflow)
            ui_tile_fs_pending = 0;                         /* L was pressed again: no full screen */
        else if (ui_vflow_p < 0.02) {
            ui_tile_fs_pending = 0;
            if (!is_full_screen)
                toggle_full_screen(is);
        }
    }
    if (is->ui_hold) {
        if (!is->ui_held) {
            if (!is->paused)
                toggle_pause(is);
            is->ui_held = 1;
            is->force_refresh = 1;
        } else if (is->ui_held == 1 && !is->paused) {      /* play was pressed on the last picture: from the start */
            is->ui_held = 2;
            is->ui_hold = 0;
            stream_seek(is, is->ic->start_time != AV_NOPTS_VALUE ? is->ic->start_time : 0, 0, 0);
        }
    } else if (is->ui_held == 2 && !is->seek_req && !is->eof) {
        is->ui_held = 0;
    }
    if (is->paused && !seen) {
        seen = 1;
        if (vid && q_count >= 2 && q_pos >= 0 && !ui_vflow) {
            ui_vflow_set(is, 1);
            ui_vflow_auto = 1;
        }
    } else if (!is->paused && !is->step) {
        if (seen && !unpaused_at)
            unpaused_at = now;
        if (seen && now - unpaused_at > 60000) {          /* playing for a moment (a seek while paused flickers) */
            seen = 0;
            unpaused_at = 0;
            if (ui_vflow_auto) {
                ui_vflow_auto = 0;
                ui_vflow_set(is, 0);
            }
        }
    } else {
        unpaused_at = 0;
    }
}

/* A tick or a refresh that takes long is named in the terminal, so a stutter can be traced to what caused it */
#define UI_TIMED(call) do { \
        int64_t t_ = av_gettime_relative(); \
        call; \
        t_ = av_gettime_relative() - t_; \
        if (t_ > 40000) \
            av_log(NULL, AV_LOG_WARNING, "ffplay-custom: slow: %s took %d ms\n", #call, (int)(t_ / 1000)); \
    } while (0)

static void refresh_loop_wait_event(VideoState *is, SDL_Event *event) {
    double remaining_time = 0.0;
    SDL_PumpEvents();
    while (!SDL_PeepEvents(event, 1, SDL_GETEVENT, SDL_FIRSTEVENT, SDL_LASTEVENT)) {
        if (!cursor_hidden && !ui_hover && !ui_drag && !ui_menu_open && !ui_prefs_open && av_gettime_relative() - cursor_last_shown > CURSOR_HIDE_DELAY) {
            SDL_ShowCursor(0);
            cursor_hidden = 1;
        }
        if (remaining_time > 0.0)
            av_usleep((int64_t)(remaining_time * 1000000.0));
        UI_TIMED(ui_aspect_tick(is));
        UI_TIMED(ui_inbox_tick(is));
        UI_TIMED(ui_menu_tick(is));
        UI_TIMED(ui_power_tick(is));
        UI_TIMED(ui_sleep_tick(is));
        UI_TIMED(ui_xfade_tick(is));
        UI_TIMED(ui_pause_tick(is));
        UI_TIMED(ui_ks_tick(is));
        UI_TIMED(ui_th_tick(is));
        UI_TIMED(ui_cover_tick(is));
        UI_TIMED(ui_mpris_tick(is));
        if (ui_q_autoscroll())
            is->force_refresh = 1;
        if (is->paused && !is->force_refresh) {     /* paused: the picture is still, but the bars show, move and hide, so keep drawing while they are active */
            static int64_t forced_at = 0;
            int64_t tnow = av_gettime_relative();

            if ((ui_hover || ui_drag || tnow - cursor_last_shown < CURSOR_HIDE_DELAY + 800000) && tnow - forced_at > 30000) {
                forced_at = tnow;
                is->force_refresh = 1;
            }
        }
        if (ui_seek_want)
            ui_seek_flush(is, ui_drag != 1);
        remaining_time = REFRESH_RATE;
        if (is->show_mode != SHOW_MODE_NONE && (!is->paused || is->force_refresh))
            UI_TIMED(video_refresh(is, &remaining_time));
        SDL_PumpEvents();
    }
}

static av_unused void seek_chapter(VideoState *is, int incr)
{
    int64_t pos = get_master_clock(is) * AV_TIME_BASE;
    int i;

    if (!is->ic->nb_chapters)
        return;

    /* find the current chapter */
    for (i = 0; i < is->ic->nb_chapters; i++) {
        AVChapter *ch = is->ic->chapters[i];
        if (av_compare_ts(pos, AV_TIME_BASE_Q, ch->start, ch->time_base) < 0) {
            i--;
            break;
        }
    }

    i += incr;
    i = FFMAX(i, 0);
    if (i >= is->ic->nb_chapters)
        return;

    av_log(NULL, AV_LOG_VERBOSE, "Seeking to chapter %d.\n", i);
    stream_seek(is, av_rescale_q(is->ic->chapters[i]->start, is->ic->chapters[i]->time_base,
                                 AV_TIME_BASE_Q), 0, 0);
}

/* handle an event sent by the GUI */
/* Snap the window to the video's aspect ratio once the user stops resizing. */
static void ui_aspect_tick(VideoState *is)
{
    AVRational sar;
    double ar;
    int w, h, nw, nh;

    if (!ui_aspect_due || av_gettime_relative() < ui_aspect_due)
        return;
    ui_aspect_due = 0;
    if (av_gettime_relative() - ui_fs_toggle_at < 1500000)
        return;                                 /* the window is coming back from full screen: it already has its size */
    if (cfg_keep_window && ui_user_sized && av_gettime_relative() < ui_prog_until)
        return;                                 /* our own size change (the saved window, a new item): the size stays as it is */

    if (is_full_screen || !is->video_st || !is->ic)
        return;
    if (SDL_GetWindowFlags(window) & SDL_WINDOW_MAXIMIZED)
        return;
    if (!is->video_st->codecpar->width || !is->video_st->codecpar->height)
        return;

    SDL_GetWindowSize(window, &w, &h);
    if (w < 260 || h <= UI_BAR_H * 3)
        return;
    {                                           /* a window the system tiled or maximized keeps the size it was given */
        SDL_Rect area;

        if (SDL_GetDisplayUsableBounds(SDL_GetWindowDisplayIndex(window), &area) == 0 && h >= area.h - 40)
            return;
    }

    sar = av_guess_sample_aspect_ratio(is->ic, is->video_st, NULL);
    if (sar.num <= 0 || sar.den <= 0) {
        sar.num = 1;
        sar.den = 1;
    }
    ar = (double)is->video_st->codecpar->width * sar.num /
         ((double)is->video_st->codecpar->height * sar.den);

    nw = w;
    nh = (int)(w / ar + 0.5);
    if (nh > h) {           /* too tall: fit inside the dragged size instead */
        nh = h;
        nw = (int)(h * ar + 0.5);
    }
    if (FFABS(nw - w) <= 1 && FFABS(nh - h) <= 1)
        return;
    ui_prog_until = av_gettime_relative() + 1500000;
    ui_prog_w = nw;
    ui_prog_h = nh;
    if (cfg_keep_window && ui_user_sized) {     /* the snapped size is the size the user chose */
        ui_keep_w = nw;
        ui_keep_h = nh;
    }
    SDL_SetWindowSize(window, nw, nh);
}

/* ---- move and resize the borderless window with the mouse (not in fullscreen) ----
   The title bar moves the window (the window manager does the move, see ui_hit_test). Drag an edge or corner to resize it.
   The size always follows the video's aspect ratio, so there are no black bars. */
#define UI_EDGE_L 1
#define UI_EDGE_R 2
#define UI_EDGE_T 4
#define UI_EDGE_B 8

static int ui_win_mode = 0;     /* 0 = nothing, 1 = moving, 2 = resizing */
static int ui_win_edges = 0;    /* which edges are being dragged (UI_EDGE_*) */
static int ui_gx0, ui_gy0;      /* mouse position on screen when the drag started */
static int ui_wx0, ui_wy0;      /* window position when the drag started */
static int ui_ww0, ui_wh0;      /* window size when the drag started */
static SDL_Cursor *ui_cursors[5];
static int ui_cursor_now = 0;

/* Width / height of the video picture, or 0 if there is no video (audio file) */
static double ui_video_aspect(VideoState *is)
{
    AVRational sar;

    if (!is || !is->video_st || !is->ic ||
        !is->video_st->codecpar->width || !is->video_st->codecpar->height)
        return 0.0;
    sar = av_guess_sample_aspect_ratio(is->ic, is->video_st, NULL);
    if (sar.num <= 0 || sar.den <= 0) {
        sar.num = 1;
        sar.den = 1;
    }
    return (double)is->video_st->codecpar->width * sar.num /
           ((double)is->video_st->codecpar->height * sar.den);
}

/* Which window edges is the point (x, y) near? Returns UI_EDGE_* values added together. */
static int ui_edges_at(int x, int y)
{
    int w, h;
    int e = 0;
    int c = 20;     /* size of the corner zones: only the corners resize the window */

    SDL_GetWindowSize(window, &w, &h);
    if (x < c && y < c)           e = UI_EDGE_L | UI_EDGE_T;
    if (x >= w - c && y < c)      e = UI_EDGE_R | UI_EDGE_T;
    if (x < c && y >= h - c)      e = UI_EDGE_L | UI_EDGE_B;
    if (x >= w - c && y >= h - c) e = UI_EDGE_R | UI_EDGE_B;
    return e;
}

/* Show the right mouse cursor for the edges under the mouse */
static void ui_set_cursor(int edges)
{
    int which = 0;      /* 0 = normal arrow */

    if (edges == UI_EDGE_L || edges == UI_EDGE_R)
        which = 1;      /* left-right arrows */
    else if (edges == UI_EDGE_T || edges == UI_EDGE_B)
        which = 2;      /* up-down arrows */
    else if (edges == (UI_EDGE_L | UI_EDGE_T) || edges == (UI_EDGE_R | UI_EDGE_B))
        which = 3;      /* diagonal, top-left to bottom-right */
    else if (edges)
        which = 4;      /* diagonal, top-right to bottom-left */

    if (which == ui_cursor_now)
        return;
    ui_cursor_now = which;
    if (!ui_cursors[which]) {
        static const SDL_SystemCursor kinds[5] = {
            SDL_SYSTEM_CURSOR_ARROW, SDL_SYSTEM_CURSOR_SIZEWE, SDL_SYSTEM_CURSOR_SIZENS,
            SDL_SYSTEM_CURSOR_SIZENWSE, SDL_SYSTEM_CURSOR_SIZENESW
        };
        ui_cursors[which] = SDL_CreateSystemCursor(kinds[which]);
    }
    if (ui_cursors[which])
        SDL_SetCursor(ui_cursors[which]);
}

/* Work out the new window size and position while dragging an edge or corner */
static void ui_resize_to(VideoState *is, int gx, int gy)
{
    double ar = ui_video_aspect(is);
    int dx = gx - ui_gx0;
    int dy = gy - ui_gy0;
    int horiz = ui_win_edges & (UI_EDGE_L | UI_EDGE_R);
    int vert  = ui_win_edges & (UI_EDGE_T | UI_EDGE_B);
    int x = ui_wx0, y = ui_wy0;
    int w, h, wx, hy;
    SDL_Rect area;

    /* Width and height the mouse is asking for */
    wx = ui_ww0;
    hy = ui_wh0;
    if (ui_win_edges & UI_EDGE_R) wx += dx;
    if (ui_win_edges & UI_EDGE_L) wx -= dx;
    if (ui_win_edges & UI_EDGE_B) hy += dy;
    if (ui_win_edges & UI_EDGE_T) hy -= dy;
    wx = FFMAX(wx, 320);
    hy = FFMAX(hy, 180);

    /* Biggest size that fits on the screen */
    SDL_GetDisplayUsableBounds(SDL_GetWindowDisplayIndex(window), &area);

    if (ar > 0.0) {
        /* Video: choose the width, then get the height from the aspect ratio */
        int from_h = (int)(hy * ar + 0.5);      /* width that matches the height asked for */

        if (horiz && !vert)
            w = wx;
        else if (vert && !horiz)
            w = from_h;
        else
            w = FFMAX(wx, from_h);              /* corner: follow the bigger one */
        w = av_clip(w, 320, area.w);
        h = (int)(w / ar + 0.5);
        if (h > area.h) {                       /* too tall for the screen */
            h = area.h;
            w = (int)(h * ar + 0.5);
        }
    } else {
        /* No video picture (audio file): resize freely */
        w = FFMIN(wx, area.w);
        h = FFMIN(hy, area.h);
    }

    /* Left and top edges: keep the opposite side where it was */
    if (ui_win_edges & UI_EDGE_L) x = ui_wx0 + ui_ww0 - w;
    if (ui_win_edges & UI_EDGE_T) y = ui_wy0 + ui_wh0 - h;

    SDL_SetWindowPosition(window, x, y);
    SDL_SetWindowSize(window, w, h);
}

/* ---- the title bar: a translucent strip across the top of the window (windowed mode only), drawn over the picture like the seek bar ----
   Close at the left, fullscreen at the right, the name of what plays in the middle.
   The strip between the buttons moves the window: ui_hit_test tells SDL that it is a drag area, so the window manager
   does the move itself. That is why dragging it to the top of the screen maximizes the window, and to the left or right
   side tiles it, like any other window of the desktop. */
#define UI_TB_H     30                  /* height of the strip */
#define UI_TB_BTN   40                  /* width of each button */
#define UI_TB_PAD   22                  /* the corners of the window (to resize it) are left of and right of the buttons */
#define UI_TB_EDGE  5                   /* the top rows stay the window's resize edge */

static int ui_tb_on = 0;                /* 1 while the strip is drawn */
static int ui_tb_hover = 0;             /* 0 = nothing, 1 = close, 2 = fullscreen */

/* One line, w pixels thick, from (x0, y0) to (x1, y1), in the current draw color */
static void ui_tb_line(double x0, double y0, double x1, double y1, double w)
{
    SDL_Vertex v[4];
    int idx[6] = { 0, 1, 2, 1, 3, 2 }, k;
    Uint8 cr, cg, cb, ca;
    double dx = x1 - x0, dy = y1 - y0, len = sqrt(dx * dx + dy * dy), nx, ny;

    if (len < 0.01)
        return;
    nx = -dy / len * w / 2.0;
    ny = dx / len * w / 2.0;
    SDL_GetRenderDrawColor(renderer, &cr, &cg, &cb, &ca);
    v[0].position.x = (float)(x0 + nx);
    v[0].position.y = (float)(y0 + ny);
    v[1].position.x = (float)(x0 - nx);
    v[1].position.y = (float)(y0 - ny);
    v[2].position.x = (float)(x1 + nx);
    v[2].position.y = (float)(y1 + ny);
    v[3].position.x = (float)(x1 - nx);
    v[3].position.y = (float)(y1 - ny);
    for (k = 0; k < 4; k++) {
        v[k].color.r = cr;
        v[k].color.g = cg;
        v[k].color.b = cb;
        v[k].color.a = ca;
        v[k].tex_coord.x = 0;
        v[k].tex_coord.y = 0;
    }
    SDL_RenderGeometry(renderer, NULL, v, 4, idx, 6);
}

static void ui_titlebar_draw(VideoState *is)
{
    SDL_Rect row;
    char name[300];
    int w, h, y, a, sx, sy, cy = UI_TB_H / 2, cx1 = UI_TB_PAD + UI_TB_BTN / 2, cx2;

    ui_tb_on = 0;
    ui_tb_hover = 0;
    if (!window || cursor_hidden || is_full_screen)     /* windowed mode only; hides with the cursor like the seek bar */
        return;
    SDL_GetWindowSize(window, &w, &h);
    if (w < 260 || h < UI_BAR_H * 3)
        return;
    ui_tb_on = 1;
    cx2 = w - UI_TB_PAD - UI_TB_BTN / 2;
    {                                           /* which button is the mouse over? */
        int mx, my;

        SDL_GetMouseState(&mx, &my);
        if (my >= UI_TB_EDGE && my < UI_TB_H)
            ui_tb_hover = (mx >= UI_TB_PAD && mx < UI_TB_PAD + UI_TB_BTN) ? 1 :
                          (mx >= w - UI_TB_PAD - UI_TB_BTN && mx < w - UI_TB_PAD) ? 2 : 0;
    }
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    row.x = 0;
    row.w = w;
    row.h = 1;
    for (y = 0; y < UI_TB_H + 10; y++) {        /* a dark glass strip that fades out along its lower edge */
        a = y < UI_TB_H ? 125 : 125 * (UI_TB_H + 10 - y) / 10;
        row.y = y;
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, a);
        SDL_RenderFillRect(renderer, &row);
    }

    if (ui_tb_hover)                            /* a soft round highlight under the button the mouse is over */
        ui_fan(ui_tb_hover == 1 ? cx1 : cx2, cy, 12, 0, 6.28318531, 28, 255, 255, 255, 40);

    SDL_SetRenderDrawColor(renderer, 245, 245, 245, ui_tb_hover == 1 ? 255 : 200);      /* close: a cross */
    ui_tb_line(cx1 - 5, cy - 5, cx1 + 5, cy + 5, 1.8);
    ui_tb_line(cx1 - 5, cy + 5, cx1 + 5, cy - 5, 1.8);

    SDL_SetRenderDrawColor(renderer, 245, 245, 245, ui_tb_hover == 2 ? 255 : 200);
    for (sx = -1; sx <= 1; sx += 2)
        for (sy = -1; sy <= 1; sy += 2) {
            if (!is_full_screen) {              /* four corners pointing out: go fullscreen */
                ui_tb_line(cx2 + sx * 6, cy + sy * 6, cx2 + sx * 2, cy + sy * 6, 1.8);
                ui_tb_line(cx2 + sx * 6, cy + sy * 6, cx2 + sx * 6, cy + sy * 2, 1.8);
            } else {                            /* four corners pointing in: leave fullscreen */
                ui_tb_line(cx2 + sx * 2, cy + sy * 2, cx2 + sx * 7, cy + sy * 2, 2.0);
                ui_tb_line(cx2 + sx * 2, cy + sy * 2, cx2 + sx * 2, cy + sy * 7, 2.0);
            }
        }

    if (ui_on_top)                              /* a small dot: the window stays on top */
        ui_fan(cx2 - UI_TB_BTN / 2 - 6, cy, 3, 0, 6.28318531, 16, av_clip(cfg_bar_r + 60, 0, 255),
               av_clip(cfg_bar_g + 60, 0, 255), av_clip(cfg_bar_b + 60, 0, 255), 230);
    if (is && q_pos >= 0 && q_pos < q_count)    /* the name of what plays, in the middle */
        ui_q_name(q_pos, name, sizeof(name));
    else
        snprintf(name, sizeof(name), "ffplay-custom");
    ui_fit_text(name, 14, w - 2 * (UI_TB_PAD + UI_TB_BTN + 16));
    ui_label_c(w / 2, cy, name, 14, 235, 235, 235, 210);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
}

/* Tells SDL which part of the window moves it: the strip between the two buttons. The window manager then does the move. */
static SDL_HitTestResult SDLCALL ui_hit_test(SDL_Window *win, const SDL_Point *area, void *data)
{
    int w, h;

    if (!ui_tb_on || is_full_screen)
        return SDL_HITTEST_NORMAL;
    SDL_GetWindowSize(win, &w, &h);
    if (area->y >= UI_TB_EDGE && area->y < UI_TB_H && area->x >= UI_TB_PAD + UI_TB_BTN && area->x < w - UI_TB_PAD - UI_TB_BTN)
        return SDL_HITTEST_DRAGGABLE;
    return SDL_HITTEST_NORMAL;
}

/* The window manager's own window menu (always on top, show on all workspaces, move to workspace, move, resize,
   maximize, minimize, close) at the mouse. X11 sessions: the window manager is asked with _GTK_SHOW_WINDOW_MENU. */
typedef struct {
    int type;
    unsigned long serial;
    int send_event;
    void *display;
    unsigned long window;
    unsigned long message_type;
    int format;
    long l[5];
} UiXClientMsg;

static void ui_wm_menu(void)
{
    SDL_SysWMinfo info;
    static void *xlib = NULL;
    static unsigned long (*x_atom)(void *, const char *, int);
    static unsigned long (*x_root)(void *);
    static int (*x_send)(void *, unsigned long, int, long, void *);
    static int (*x_flush)(void *);
    union { UiXClientMsg m; long pad[24]; } ev;
    int gx, gy;

    SDL_VERSION(&info.version);
    if (!window || !SDL_GetWindowWMInfo(window, &info))
        return;
    if (info.subsystem != SDL_SYSWM_X11) {      /* no window manager menu to ask for: the one thing it would give us here */
        ui_toggle_on_top();
        return;
    }
    if (!xlib) {
        xlib = dlopen("libX11.so.6", RTLD_LAZY);
        if (xlib) {
            *(void **)&x_atom = dlsym(xlib, "XInternAtom");
            *(void **)&x_root = dlsym(xlib, "XDefaultRootWindow");
            *(void **)&x_send = dlsym(xlib, "XSendEvent");
            *(void **)&x_flush = dlsym(xlib, "XFlush");
        }
    }
    if (!x_atom || !x_root || !x_send || !x_flush)
        return;
    SDL_GetGlobalMouseState(&gx, &gy);
    memset(&ev, 0, sizeof(ev));
    ev.m.type = 33;                             /* ClientMessage */
    ev.m.display = info.info.x11.display;
    ev.m.window = info.info.x11.window;
    ev.m.message_type = x_atom(info.info.x11.display, "_GTK_SHOW_WINDOW_MENU", 0);
    ev.m.format = 32;
    ev.m.l[0] = 0;                              /* the pointer device */
    ev.m.l[1] = gx;
    ev.m.l[2] = gy;
    x_send(info.info.x11.display, x_root(info.info.x11.display), 0, (1L << 20) | (1L << 19), &ev);   /* SubstructureRedirect | SubstructureNotify */
    x_flush(info.info.x11.display);
}

/* Clicks on the two buttons. Returns 1 if the click was used. */
static int ui_titlebar_mouse(VideoState *is, SDL_Event *ev)
{
    int w, h, x, y, hover = 0;

    if (!ui_tb_on || !window || (ev->type != SDL_MOUSEBUTTONDOWN && ev->type != SDL_MOUSEMOTION))
        return 0;
    SDL_GetWindowSize(window, &w, &h);
    x = ev->type == SDL_MOUSEMOTION ? ev->motion.x : ev->button.x;
    y = ev->type == SDL_MOUSEMOTION ? ev->motion.y : ev->button.y;
    if (y >= UI_TB_EDGE && y < UI_TB_H)
        hover = (x >= UI_TB_PAD && x < UI_TB_PAD + UI_TB_BTN) ? 1 : (x >= w - UI_TB_PAD - UI_TB_BTN && x < w - UI_TB_PAD) ? 2 : 0;
    if (ev->type == SDL_MOUSEMOTION) {
        if (hover != ui_tb_hover && is)
            is->force_refresh = 1;
        ui_tb_hover = hover;
        return 0;                               /* the others still see the movement */
    }
    if (ev->button.button == SDL_BUTTON_RIGHT && y < UI_TB_H) {
        ui_wm_menu();                           /* right click on the title bar: the window manager's menu */
        return 1;
    }
    if (ev->button.button != SDL_BUTTON_LEFT || !hover)
        return 0;
    if (hover == 1) {
        SDL_Event quit;

        memset(&quit, 0, sizeof(quit));
        quit.type = SDL_QUIT;
        SDL_PushEvent(&quit);                   /* the same as closing the window any other way */
    } else {
        toggle_full_screen(is);
        if (is)
            is->force_refresh = 1;
    }
    return 1;
}

/* Mouse events for resizing the window by its edges and corners (moving it is the title bar's job).
   Returns 1 if the event was used here, 0 if normal handling should go on. */
static int ui_window_mouse(VideoState *is, SDL_Event *ev)
{
    int gx, gy;
    int edges;

    if (is_full_screen) {
        if (ui_win_mode) {
            ui_win_mode = 0;
            SDL_CaptureMouse(SDL_FALSE);
        }
        ui_set_cursor(0);
        return 0;
    }

    SDL_GetGlobalMouseState(&gx, &gy);

    if (ev->type == SDL_MOUSEBUTTONDOWN) {
        if (ev->button.button != SDL_BUTTON_LEFT)
            return 0;
        edges = ui_edges_at(ev->button.x, ev->button.y);
        if (!edges)
            return 0;                   /* only the edges and corners are ours; a click on the picture goes on */
        ui_win_mode = 2;
        ui_win_edges = edges;
        ui_gx0 = gx;
        ui_gy0 = gy;
        SDL_GetWindowPosition(window, &ui_wx0, &ui_wy0);
        SDL_GetWindowSize(window, &ui_ww0, &ui_wh0);
        SDL_CaptureMouse(SDL_TRUE);
        return 1;
    }
    if (ev->type == SDL_MOUSEMOTION) {
        if (ui_win_mode == 2) {
            ui_resize_to(is, gx, gy);
            ui_wake();
            return 1;
        }
        /* Not resizing: show a resize cursor over the edges */
        ui_set_cursor(ui_edges_at(ev->motion.x, ev->motion.y));
        return 0;
    }
    if (ev->type == SDL_MOUSEBUTTONUP && ev->button.button == SDL_BUTTON_LEFT && ui_win_mode) {
        ui_win_mode = 0;
        SDL_CaptureMouse(SDL_FALSE);
        return 1;
    }
    return 0;
}

/* The idle screen: logo and menu. Returns when something has been added to the queue. */
static void ui_idle_loop(void)
{
    SDL_Event ev;

    if (!window)
        do_exit(NULL);              /* no window to show (-nodisp) */

    /* The window starts hidden, so show it. Keep its size if it was already open. */
    if (!ui_shown_once && (!SDL_GetWindowFlags(window) || !(SDL_GetWindowFlags(window) & SDL_WINDOW_SHOWN))) {
        SDL_SetWindowTitle(window, "ffplay-custom");
        if (!is_full_screen)
            SDL_SetWindowSize(window, 960, 540);
        SDL_ShowWindow(window);
        ui_shown_once = 1;
        if (is_full_screen)
            SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP);
    }
    if (cursor_hidden) {
        SDL_ShowCursor(1);
        cursor_hidden = 0;
    }
    SDL_SetWindowTitle(window, "ffplay-custom");      /* the idle screen has no item name */
    ui_idle = 1;
    ui_menu_open = 0;
    ui_menu_hover = -1;
    ui_q_open = 0;
    ui_info_open = 0;
    ui_open_open = 0;
    ui_ctx_open = 0;
    ui_q_drag = -1;

    /* wait here until there is something to play (after a sleep stop: until the user picks something) */
    while (queue_next() >= q_count || (q_hold && q_forced < 0)) {
        ui_inbox_tick(NULL);
        ui_power_tick(NULL);
        ui_sleep_tick(NULL);
        ui_mpris_tick(NULL);
        ui_q_autoscroll();
        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
            case SDL_QUIT:
                do_exit(NULL);
                break;
            case SDL_KEYDOWN:
                ev.key.keysym.sym = ui_key_translate(ev.key.keysym.sym);   /* the keys chosen in settings.conf */
                if (ev.key.keysym.sym == SDLK_ESCAPE) {
                    if (ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open) {
                        ui_prefs_open = 0;
                        ui_q_open = 0;
                        ui_info_open = 0;
                        ui_open_open = 0;
                        ui_ctx_open = 0;
                    } else if (is_full_screen) {
                        toggle_full_screen(NULL);
                    }
                } else if (ev.key.keysym.sym == SDLK_q)
                    do_exit(NULL);
                else if (ev.key.keysym.sym == SDLK_f)
                    toggle_full_screen(NULL);
                break;
            case SDL_WINDOWEVENT:
                if (ev.window.event == SDL_WINDOWEVENT_SIZE_CHANGED) {
                    screen_width  = ev.window.data1;    /* the next video opens at this size */
                    screen_height = ev.window.data2;
                    ui_note_size(ev.window.data1, ev.window.data2);
                }
                break;
            case SDL_MOUSEWHEEL:
                ui_queue_wheel(&ev);
                break;
            case SDL_MOUSEBUTTONDOWN:
            case SDL_MOUSEMOTION:
            case SDL_MOUSEBUTTONUP:
                if (ev.type == SDL_MOUSEBUTTONUP && ui_queue_release(&ev))
                    break;
                if (ev.type != SDL_MOUSEBUTTONUP && ui_titlebar_mouse(NULL, &ev))
                    break;
                if (ev.type != SDL_MOUSEBUTTONUP && ui_menu_mouse(NULL, &ev))
                    break;
                ui_window_mouse(NULL, &ev);     /* edges to resize */
                break;
            default:
                break;
            }
        }
        ui_glass_frame(NULL);
        SDL_Delay(16);
    }
    q_hold = 0;
    ui_idle = 0;
}

/* Seek by incr seconds: the same as the Left and Right arrow keys */
static void ui_seek_relative(VideoState *is, double incr)
{
    double pos;

    if (seek_by_bytes) {
        pos = -1;
        if (pos < 0 && is->video_stream >= 0)
            pos = frame_queue_last_pos(&is->pictq);
        if (pos < 0 && is->audio_stream >= 0)
            pos = frame_queue_last_pos(&is->sampq);
        if (pos < 0)
            pos = avio_tell(is->ic->pb);
        if (is->ic->bit_rate)
            incr *= is->ic->bit_rate / 8.0;
        else
            incr *= 180000.0;
        pos += incr;
        stream_seek(is, pos, incr, 1);
    } else {
        if (ui_ks_want || is->seek_req || is->prec_v || is->prec_a || av_gettime_relative() - ui_ks_issued < 200000) {
            pos = ui_ks_target;         /* going on from the last step: the clock is not valid while a seek is on its way */
        } else {
            pos = get_master_clock(is);
            if (isnan(pos))
                pos = (double)is->seek_pos / AV_TIME_BASE;
        }
        pos += incr;
        if (is->ic->start_time != AV_NOPTS_VALUE && pos < is->ic->start_time / (double)AV_TIME_BASE)
            pos = is->ic->start_time / (double)AV_TIME_BASE;
        ui_ks_target = pos;
        ui_ks_is = is;
        ui_ks_want = 1;
        is->force_refresh = 1;
    }
}

/* The mouse wheel (or a touchpad swipe), as chosen in Preferences: volume, seek, or nothing */
static void ui_wheel_action(VideoState *is, SDL_Event *ev)
{
    static double acc = 0.0;
    static int64_t last = 0;
    int64_t now = av_gettime_relative();
    double amount;
    int steps, i;

    if (!cfg_wheel || ui_menu_open || ui_prefs_open)
        return;
    {
        double ax, ay;
#if SDL_VERSION_ATLEAST(2, 0, 18)
        ax = ev->wheel.preciseX;
        ay = ev->wheel.preciseY;
#else
        ax = ev->wheel.x;
        ay = ev->wheel.y;
#endif
        if (FFABS(ax) > FFABS(ay)) {            /* a sideways swipe moves through the queue */
            ui_flow_swipe(is, ev);
            return;
        }
    }
#if SDL_VERSION_ATLEAST(2, 0, 18)
    amount = ev->wheel.preciseY;
#else
    amount = ev->wheel.y;
#endif
    if (ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED)
        amount = -amount;
    if (now - last > 300000 || amount * acc < 0.0)
        acc = 0.0;                              /* a new swipe, or the other direction: start from zero */
    last = now;
    acc += amount;
    steps = (int)acc;                           /* whole notches only: a touchpad adds up small moves */
    if (!steps)
        return;
    acc -= steps;
    if (cfg_wheel == 1) {
        for (i = 0; i < FFABS(steps); i++)
            update_volume(is, steps > 0 ? -1 : 1, SDL_VOLUME_STEP);        /* reversed */
    } else {
        ui_seek_relative(is, steps * cfg_seek);
    }
    ui_wake();                                  /* the bars show what happened */
    is->force_refresh = 1;
}

static void event_loop(VideoState *cur_stream)
{
    SDL_Event event;
    double incr, pos, frac;

    for (;;) {
        double x;
        refresh_loop_wait_event(cur_stream, &event);
        switch (event.type) {
        case SDL_KEYDOWN:
            event.key.keysym.sym = ui_key_translate(event.key.keysym.sym);   /* the keys chosen in settings.conf */
            if (event.key.keysym.sym == SDLK_ESCAPE) {
                if (ui_menu_open || ui_prefs_open || ui_q_open || ui_info_open || ui_open_open || ui_ctx_open) {
                    ui_menu_open = 0;
                    ui_prefs_open = 0;
                    ui_q_open = 0;
                    ui_info_open = 0;
                    ui_open_open = 0;
                    ui_ctx_open = 0;
                    cur_stream->force_refresh = 1;
                } else if (is_full_screen) {
                    toggle_full_screen(cur_stream);
                    cur_stream->force_refresh = 1;
                }
                break;
            }
            if (exit_on_keydown || event.key.keysym.sym == SDLK_q) {
                do_exit(cur_stream);
                break;
            }
            // If we don't yet have a window, skip all key events, because read_thread might still be initializing...
            if (!cur_stream->width)
                continue;
            ui_wake();
            switch (event.key.keysym.sym) {
            case SDLK_f:
                toggle_full_screen(cur_stream);
                cur_stream->force_refresh = 1;
                break;
            case SDLK_n:
            case SDLK_PERIOD:
                ui_user_skip = 1;
                q_step = 1;
                ui_end_stream(cur_stream);
                return;
            case SDLK_p:
            case SDLK_COMMA:
                ui_user_skip = 1;
                q_step = -1;
                ui_end_stream(cur_stream);
                return;
            case SDLK_SPACE:
                toggle_pause(cur_stream);
                break;
            case SDLK_m:
                toggle_mute(cur_stream);
                break;
            case SDLK_KP_MULTIPLY:
            case SDLK_0:
                update_volume(cur_stream, 1, SDL_VOLUME_STEP);
                break;
            case SDLK_KP_DIVIDE:
            case SDLK_9:
                update_volume(cur_stream, -1, SDL_VOLUME_STEP);
                break;
            case SDLK_s: // S: Step to next frame
                step_to_next_frame(cur_stream);
                break;
            case SDLK_a:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_AUDIO);
                break;
            case SDLK_v:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_VIDEO);
                break;
            case SDLK_c:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_VIDEO);
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_AUDIO);
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_SUBTITLE);
                break;
            case SDLK_o:                /* on top of the other windows, or not */
                ui_toggle_on_top();
                break;
            case SDLK_t:
                stream_cycle_channel(cur_stream, AVMEDIA_TYPE_SUBTITLE);
                break;
            case SDLK_l:                /* the queue view over a video (with audio it is always there): the video keeps playing in its tile */
                if (cur_stream->video_st && !(cur_stream->video_st->disposition & AV_DISPOSITION_ATTACHED_PIC)) {
                    ui_vflow = !ui_vflow;
                    ui_vflow_auto = 0;          /* L was pressed: it stays until L is pressed again */
                    ui_vflow_t = 0;
                    ui_bd_key[0] = 0;           /* the backdrop takes its colors from the picture of this moment */
                    ui_flow_pos = ui_flow_target = q_pos;       /* the row starts at the playing video, no gliding in */
                    ui_flow_last_q = q_pos;
                    ui_flow_touch = 0;
                    cur_stream->force_refresh = 1;
                }
                break;
            case SDLK_w:
                if (cur_stream->show_mode == SHOW_MODE_VIDEO && cur_stream->vfilter_idx < nb_vfilters - 1) {
                    if (++cur_stream->vfilter_idx >= nb_vfilters)
                        cur_stream->vfilter_idx = 0;
                } else {
                    cur_stream->vfilter_idx = 0;
                    toggle_audio_display(cur_stream);
                }
                break;
            case SDLK_PAGEUP:
            case SDLK_PAGEDOWN:
                break;                  /* Page Up and Page Down do nothing */
            case SDLK_LEFT:
                incr = -cfg_seek;
                goto do_seek;
            case SDLK_RIGHT:
                incr = cfg_seek;
                goto do_seek;
            case SDLK_UP:
                update_volume(cur_stream, 1, SDL_VOLUME_STEP);
                break;
            case SDLK_DOWN:
                update_volume(cur_stream, -1, SDL_VOLUME_STEP);
                break;
            do_seek:
                    if (seek_by_bytes) {
                        pos = -1;
                        if (pos < 0 && cur_stream->video_stream >= 0)
                            pos = frame_queue_last_pos(&cur_stream->pictq);
                        if (pos < 0 && cur_stream->audio_stream >= 0)
                            pos = frame_queue_last_pos(&cur_stream->sampq);
                        if (pos < 0)
                            pos = avio_tell(cur_stream->ic->pb);
                        if (cur_stream->ic->bit_rate)
                            incr *= cur_stream->ic->bit_rate / 8.0;
                        else
                            incr *= 180000.0;
                        pos += incr;
                        stream_seek(cur_stream, pos, incr, 1);
                    } else {
                        ui_seek_relative(cur_stream, incr);
                    }
                break;
            default:
                break;
            }
            break;
        case SDL_MOUSEWHEEL:
            if (ui_queue_wheel(&event))
                cur_stream->force_refresh = 1;     /* the queue list scrolls */
            else
                ui_wheel_action(cur_stream, &event);
            break;
        case SDL_MOUSEBUTTONUP:
            if (ui_queue_release(&event)) {
                cur_stream->force_refresh = 1;
                break;
            }
            if (ui_window_mouse(cur_stream, &event))
                break;
            ui_mouse(cur_stream, &event);
            break;
        case SDL_MOUSEBUTTONDOWN:
            if (ui_titlebar_mouse(cur_stream, &event) || ui_menu_mouse(cur_stream, &event) ||
                ui_window_mouse(cur_stream, &event) || ui_mouse(cur_stream, &event))
                break;
            if (exit_on_mousedown) {
                do_exit(cur_stream);
                break;
            }
            if (event.button.button == SDL_BUTTON_LEFT) {
                static int64_t last_mouse_left_click = 0;
                if (av_gettime_relative() - last_mouse_left_click <= 500000) {
                    toggle_full_screen(cur_stream);
                    cur_stream->force_refresh = 1;
                    last_mouse_left_click = 0;
                } else {
                    last_mouse_left_click = av_gettime_relative();
                }
            }
        case SDL_MOUSEMOTION:
            if (event.type == SDL_MOUSEMOTION &&
                (ui_titlebar_mouse(cur_stream, &event) || ui_menu_mouse(cur_stream, &event) ||
                 ui_window_mouse(cur_stream, &event) || ui_mouse(cur_stream, &event)))
                break;
            if (cursor_hidden) {
                SDL_ShowCursor(1);
                cursor_hidden = 0;
            }
            cursor_last_shown = av_gettime_relative();
            /* Right-click seeking is disabled; the old seek code below never runs */
            break;
            if (event.type == SDL_MOUSEBUTTONDOWN) {
                if (event.button.button != SDL_BUTTON_RIGHT)
                    break;
                x = event.button.x;
            } else {
                if (!(event.motion.state & SDL_BUTTON_RMASK))
                    break;
                x = event.motion.x;
            }
                if (seek_by_bytes || cur_stream->ic->duration <= 0) {
                    uint64_t size =  avio_size(cur_stream->ic->pb);
                    stream_seek(cur_stream, size*x/cur_stream->width, 0, 1);
                } else {
                    int64_t ts;
                    int ns, hh, mm, ss;
                    int tns, thh, tmm, tss;
                    tns  = cur_stream->ic->duration / 1000000LL;
                    thh  = tns / 3600;
                    tmm  = (tns % 3600) / 60;
                    tss  = (tns % 60);
                    frac = x / cur_stream->width;
                    ns   = frac * tns;
                    hh   = ns / 3600;
                    mm   = (ns % 3600) / 60;
                    ss   = (ns % 60);
                    av_log(NULL, AV_LOG_INFO,
                           "Seek to %2.0f%% (%2d:%02d:%02d) of total duration (%2d:%02d:%02d)       \n", frac*100,
                            hh, mm, ss, thh, tmm, tss);
                    ts = frac * cur_stream->ic->duration;
                    if (cur_stream->ic->start_time != AV_NOPTS_VALUE)
                        ts += cur_stream->ic->start_time;
                    stream_seek(cur_stream, ts, 0, 0);
                }
            break;
        case SDL_WINDOWEVENT:
            switch (event.window.event) {
                case SDL_WINDOWEVENT_SHOWN:
                case SDL_WINDOWEVENT_RESTORED:
                case SDL_WINDOWEVENT_FOCUS_GAINED:
                case SDL_WINDOWEVENT_ENTER:
                    ui_vsync_set(1);        /* the window is in sight again */
                    cur_stream->force_refresh = 1;
                    break;
                case SDL_WINDOWEVENT_LEAVE:
                    ui_hover = 0;
                    ui_hov_x = -1;
                    break;
                case SDL_WINDOWEVENT_SIZE_CHANGED:
                    screen_width  = cur_stream->width  = event.window.data1;
                    screen_height = cur_stream->height = event.window.data2;
                    ui_aspect_due = av_gettime_relative() + 250000;
                    ui_note_size(event.window.data1, event.window.data2);      /* the user sized or tiled the window? */
                    if (cur_stream->vis_texture) {
                        SDL_DestroyTexture(cur_stream->vis_texture);
                        cur_stream->vis_texture = NULL;
                    }
                case SDL_WINDOWEVENT_EXPOSED:
                    cur_stream->force_refresh = 1;
            }
            break;
        case SDL_QUIT:
            do_exit(cur_stream);
            break;
        case FF_QUIT_EVENT:
            /* The item that was started early ended or failed: forget it and carry on with this one */
            if (xf_stream && event.user.data1 == xf_stream) {
                cur_stream->xf_gain = 1.0f;
                xf_failed = xf_name;
                ui_xf_abort();
                break;
            }
            /* The file ended, or n / p / Open was used: the main loop starts the next item */
            if (event.user.data1 != cur_stream)
                break;                  /* leftover from an earlier stream */
            ui_end_stream(cur_stream);
            return;
        default:
            break;
        }
    }
}

static int opt_width(void *optctx, const char *opt, const char *arg)
{
    double num;
    int ret = parse_number(opt, arg, OPT_INT64, 1, INT_MAX, &num);
    if (ret < 0)
        return ret;

    screen_width = num;
    return 0;
}

static int opt_height(void *optctx, const char *opt, const char *arg)
{
    double num;
    int ret = parse_number(opt, arg, OPT_INT64, 1, INT_MAX, &num);
    if (ret < 0)
        return ret;

    screen_height = num;
    return 0;
}

static int opt_format(void *optctx, const char *opt, const char *arg)
{
    file_iformat = av_find_input_format(arg);
    if (!file_iformat) {
        av_log(NULL, AV_LOG_FATAL, "Unknown input format: %s\n", arg);
        return AVERROR(EINVAL);
    }
    return 0;
}

static int opt_sync(void *optctx, const char *opt, const char *arg)
{
    if (!strcmp(arg, "audio"))
        av_sync_type = AV_SYNC_AUDIO_MASTER;
    else if (!strcmp(arg, "video"))
        av_sync_type = AV_SYNC_VIDEO_MASTER;
    else if (!strcmp(arg, "ext"))
        av_sync_type = AV_SYNC_EXTERNAL_CLOCK;
    else {
        av_log(NULL, AV_LOG_ERROR, "Unknown value for %s: %s\n", opt, arg);
        exit(1);
    }
    return 0;
}

static int opt_show_mode(void *optctx, const char *opt, const char *arg)
{
    show_mode = !strcmp(arg, "video") ? SHOW_MODE_VIDEO :
                !strcmp(arg, "waves") ? SHOW_MODE_WAVES :
                !strcmp(arg, "rdft" ) ? SHOW_MODE_RDFT  : SHOW_MODE_NONE;

    if (show_mode == SHOW_MODE_NONE) {
        double num;
        int ret = parse_number(opt, arg, OPT_INT, 0, SHOW_MODE_NB-1, &num);
        if (ret < 0)
            return ret;
        show_mode = num;
    }
    return 0;
}

static int opt_input_file(void *optctx, const char *filename)
{
    if (!strcmp(filename, "-"))
        filename = "fd:";
    queue_add_path(filename);
    if (!input_filename)
        input_filename = filename;      /* used for the window title */

    return 0;
}

static int opt_codec(void *optctx, const char *opt, const char *arg)
{
   const char *spec = strchr(opt, ':');
   if (!spec) {
       av_log(NULL, AV_LOG_ERROR,
              "No media specifier was specified in '%s' in option '%s'\n",
               arg, opt);
       return AVERROR(EINVAL);
   }
   spec++;
   switch (spec[0]) {
   case 'a' :    audio_codec_name = arg; break;
   case 's' : subtitle_codec_name = arg; break;
   case 'v' :    video_codec_name = arg; break;
   default:
       av_log(NULL, AV_LOG_ERROR,
              "Invalid media specifier '%s' in option '%s'\n", spec, opt);
       return AVERROR(EINVAL);
   }
   return 0;
}

static int dummy;

static const OptionDef options[] = {
    CMDUTILS_COMMON_OPTIONS
    { "x", HAS_ARG, { .func_arg = opt_width }, "force displayed width", "width" },
    { "y", HAS_ARG, { .func_arg = opt_height }, "force displayed height", "height" },
    { "fs", OPT_BOOL, { &is_full_screen }, "force full screen" },
    { "an", OPT_BOOL, { &audio_disable }, "disable audio" },
    { "vn", OPT_BOOL, { &video_disable }, "disable video" },
    { "sn", OPT_BOOL, { &subtitle_disable }, "disable subtitling" },
    { "ast", OPT_STRING | HAS_ARG | OPT_EXPERT, { &wanted_stream_spec[AVMEDIA_TYPE_AUDIO] }, "select desired audio stream", "stream_specifier" },
    { "vst", OPT_STRING | HAS_ARG | OPT_EXPERT, { &wanted_stream_spec[AVMEDIA_TYPE_VIDEO] }, "select desired video stream", "stream_specifier" },
    { "sst", OPT_STRING | HAS_ARG | OPT_EXPERT, { &wanted_stream_spec[AVMEDIA_TYPE_SUBTITLE] }, "select desired subtitle stream", "stream_specifier" },
    { "ss", HAS_ARG | OPT_TIME, { &start_time }, "seek to a given position in seconds", "pos" },
    { "t",  HAS_ARG | OPT_TIME, { &duration }, "play  \"duration\" seconds of audio/video", "duration" },
    { "bytes", OPT_INT | HAS_ARG, { &seek_by_bytes }, "seek by bytes 0=off 1=on -1=auto", "val" },
    { "seek_interval", OPT_FLOAT | HAS_ARG, { &seek_interval }, "set seek interval for left/right keys, in seconds", "seconds" },
    { "nodisp", OPT_BOOL, { &display_disable }, "disable graphical display" },
    { "noborder", OPT_BOOL, { &borderless }, "borderless window" },
    { "alwaysontop", OPT_BOOL, { &alwaysontop }, "window always on top" },
    { "volume", OPT_INT | HAS_ARG, { &startup_volume}, "set startup volume 0=min 100=max", "volume" },
    { "f", HAS_ARG, { .func_arg = opt_format }, "force format", "fmt" },
    { "stats", OPT_BOOL | OPT_EXPERT, { &show_status }, "show status", "" },
    { "fast", OPT_BOOL | OPT_EXPERT, { &fast }, "non spec compliant optimizations", "" },
    { "genpts", OPT_BOOL | OPT_EXPERT, { &genpts }, "generate pts", "" },
    { "drp", OPT_INT | HAS_ARG | OPT_EXPERT, { &decoder_reorder_pts }, "let decoder reorder pts 0=off 1=on -1=auto", ""},
    { "lowres", OPT_INT | HAS_ARG | OPT_EXPERT, { &lowres }, "", "" },
    { "sync", HAS_ARG | OPT_EXPERT, { .func_arg = opt_sync }, "set audio-video sync. type (type=audio/video/ext)", "type" },
    { "autoexit", OPT_BOOL | OPT_EXPERT, { &autoexit }, "exit at the end", "" },
    { "exitonkeydown", OPT_BOOL | OPT_EXPERT, { &exit_on_keydown }, "exit on key down", "" },
    { "exitonmousedown", OPT_BOOL | OPT_EXPERT, { &exit_on_mousedown }, "exit on mouse down", "" },
    { "loop", OPT_INT | HAS_ARG | OPT_EXPERT, { &loop }, "set number of times the playback shall be looped", "loop count" },
    { "framedrop", OPT_BOOL | OPT_EXPERT, { &framedrop }, "drop frames when cpu is too slow", "" },
    { "infbuf", OPT_BOOL | OPT_EXPERT, { &infinite_buffer }, "don't limit the input buffer size (useful with realtime streams)", "" },
    { "window_title", OPT_STRING | HAS_ARG, { &window_title }, "set window title", "window title" },
    { "left", OPT_INT | HAS_ARG | OPT_EXPERT, { &screen_left }, "set the x position for the left of the window", "x pos" },
    { "top", OPT_INT | HAS_ARG | OPT_EXPERT, { &screen_top }, "set the y position for the top of the window", "y pos" },
    { "vf", OPT_EXPERT | HAS_ARG, { .func_arg = opt_add_vfilter }, "set video filters", "filter_graph" },
    { "af", OPT_STRING | HAS_ARG, { &afilters }, "set audio filters", "filter_graph" },
    { "rdftspeed", OPT_INT | HAS_ARG| OPT_AUDIO | OPT_EXPERT, { &rdftspeed }, "rdft speed", "msecs" },
    { "showmode", HAS_ARG, { .func_arg = opt_show_mode}, "select show mode (0 = video, 1 = waves, 2 = RDFT)", "mode" },
    { "i", OPT_BOOL, { &dummy}, "read specified file", "input_file"},
    { "codec", HAS_ARG, { .func_arg = opt_codec}, "force decoder", "decoder_name" },
    { "acodec", HAS_ARG | OPT_STRING | OPT_EXPERT, {    &audio_codec_name }, "force audio decoder",    "decoder_name" },
    { "scodec", HAS_ARG | OPT_STRING | OPT_EXPERT, { &subtitle_codec_name }, "force subtitle decoder", "decoder_name" },
    { "vcodec", HAS_ARG | OPT_STRING | OPT_EXPERT, {    &video_codec_name }, "force video decoder",    "decoder_name" },
    { "autorotate", OPT_BOOL, { &autorotate }, "automatically rotate video", "" },
    { "find_stream_info", OPT_BOOL | OPT_INPUT | OPT_EXPERT, { &find_stream_info },
        "read and decode the streams to fill missing information with heuristics" },
    { "filter_threads", HAS_ARG | OPT_INT | OPT_EXPERT, { &filter_nbthreads }, "number of filter threads per graph" },
    { NULL, },
};

static void show_usage(void)
{
    av_log(NULL, AV_LOG_INFO, "Simple media player\n");
    av_log(NULL, AV_LOG_INFO, "usage: %s [options] input_file\n", program_name);
    av_log(NULL, AV_LOG_INFO, "\n");
}

void show_help_default(const char *opt, const char *arg)
{
    av_log_set_callback(log_callback_help);
    show_usage();
    show_help_options(options, "Main options:", 0, OPT_EXPERT, 0);
    show_help_options(options, "Advanced options:", OPT_EXPERT, 0, 0);
    printf("\n");
    show_help_children(avcodec_get_class(), AV_OPT_FLAG_DECODING_PARAM);
    show_help_children(avformat_get_class(), AV_OPT_FLAG_DECODING_PARAM);
    show_help_children(avfilter_get_class(), AV_OPT_FLAG_FILTERING_PARAM);
    printf("\nWhile playing:\n"
           "q, ESC              quit\n"
           "f                   toggle full screen\n"
           "p, SPC              pause\n"
           "m                   toggle mute\n"
           "9, 0                decrease and increase volume respectively\n"
           "/, *                decrease and increase volume respectively\n"
           "a                   cycle audio channel in the current program\n"
           "v                   cycle video channel\n"
           "t                   cycle subtitle channel in the current program\n"
           "c                   cycle program\n"
           "w                   cycle video filters or show modes\n"
           "s                   activate frame-step mode\n"
           "left/right          seek backward/forward 10 seconds or to custom interval if -seek_interval is set\n"
           "down/up             seek backward/forward 1 minute\n"
           "page down/page up   seek backward/forward 10 minutes\n"
           "right mouse click   seek to percentage in file corresponding to fraction of width\n"
           "left double-click   toggle full screen\n"
           );
}

/* Called from the main */
int main(int argc, char **argv)
{
    int flags, ret;
    VideoState *is;

    init_dynload();

    av_log_set_flags(AV_LOG_SKIP_REPEATED);
    parse_loglevel(argc, argv, options);

    /* register all codecs, demux and protocols */
#if CONFIG_AVDEVICE
    avdevice_register_all();
#endif
    avformat_network_init();

    signal(SIGINT , sigterm_handler); /* Interrupt (ANSI).    */
    signal(SIGTERM, sigterm_handler); /* Termination (ANSI).  */

    show_banner(argc, argv, options);

    ret = parse_options(NULL, argc, argv, options, opt_input_file);
    if (ret < 0)
        exit(ret == AVERROR_EXIT ? 0 : 1);

    /* No input file is fine: the idle screen is shown */

    if (display_disable) {
        video_disable = 1;
    }
    flags = SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER;
    if (audio_disable)
        flags &= ~SDL_INIT_AUDIO;
    else {
        /* Try to work around an occasional ALSA buffer underflow issue when the
         * period size is NPOT due to ALSA resampling by forcing the buffer size. */
        if (!SDL_getenv("SDL_AUDIO_ALSA_SET_BUFFER_SIZE"))
            SDL_setenv("SDL_AUDIO_ALSA_SET_BUFFER_SIZE","1", 1);
    }
    if (display_disable)
        flags &= ~SDL_INIT_VIDEO;
    /* One player at a time: if one is already running, hand it our files and leave */
    if (!ui_take_lock()) {
        int i;

        for (i = 0; i < q_count; i++) {
            char full[PATH_MAX];

            ui_inbox_send('a', realpath(q_items[i], full) ? full : q_items[i]);
        }
        exit(0);
    }

    settings_load();
    ui_key_load();
    SDL_SetHint(SDL_HINT_VIDEODRIVER, "x11,wayland");
    if (SDL_Init (flags)) {
        av_log(NULL, AV_LOG_FATAL, "Could not initialize SDL - %s\n", SDL_GetError());
        av_log(NULL, AV_LOG_FATAL, "(Did you set the DISPLAY variable?)\n");
        exit(1);
    }

    SDL_EventState(SDL_SYSWMEVENT, SDL_IGNORE);
    SDL_EventState(SDL_USEREVENT, SDL_IGNORE);

    if (!display_disable) {
        int flags = SDL_WINDOW_HIDDEN;
        if (alwaysontop)
#if SDL_VERSION_ATLEAST(2,0,5)
            flags |= SDL_WINDOW_ALWAYS_ON_TOP;
#else
            av_log(NULL, AV_LOG_WARNING, "Your SDL version doesn't support SDL_WINDOW_ALWAYS_ON_TOP. Feature will be inactive.\n");
#endif
        flags |= SDL_WINDOW_RESIZABLE;
        if (borderless)
            flags |= SDL_WINDOW_BORDERLESS;

#ifdef SDL_HINT_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR
        SDL_SetHint(SDL_HINT_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR, "0");
#endif
        window = SDL_CreateWindow(program_name, SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, default_width, default_height, flags);
        SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "linear");
        if (window) {
            renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
            if (!renderer) {
                av_log(NULL, AV_LOG_WARNING, "Failed to initialize a hardware accelerated renderer: %s\n", SDL_GetError());
                renderer = SDL_CreateRenderer(window, -1, 0);
            }
            if (renderer) {
                if (!SDL_GetRendererInfo(renderer, &renderer_info))
                    av_log(NULL, AV_LOG_VERBOSE, "Initialized %s renderer.\n", renderer_info.name);
            }
        }
        if (!window || !renderer || !renderer_info.num_texture_formats) {
            av_log(NULL, AV_LOG_FATAL, "Failed to create window or renderer: %s", SDL_GetError());
            do_exit(NULL);
        }
        SDL_SetWindowHitTest(window, ui_hit_test, NULL);        /* the title bar moves the window: the window manager does it */
    }

    /* Play the queue. The window stays open between files and when the queue is empty. */
    for (;;) {
        int next;

        if (q_pos >= 0 && q_pos < q_count && q_sleep_item && q_sleep_item == q_items[q_pos]) {
            q_sleep_item = NULL;                /* the item the sleep timer waited for is over */
            ui_sleep_sel = 0;
            if (!ui_user_skip)
                q_hold = 1;                     /* it ended by itself: stop here */
        }
        q_user_ended = ui_user_skip;
        ui_user_skip = 0;
        next = queue_next();                    /* the next item */

        if (q_hold && q_forced < 0) {           /* stopped by the sleep timer: wait for the user */
            ui_xf_abort();
            ui_idle_loop();
            continue;
        }
        if (next >= q_count) {
            ui_xf_abort();
            if (cfg_quit_when_done && q_count > 0)
                do_exit(NULL);                  /* something was played and the queue is done */
            ui_idle_loop();                     /* nothing to play: idle screen */
            continue;
        }
        q_pos = next;
        q_step = 1;
        q_played[q_pos] = 1;
        q_forced = -1;
        if (cfg_keep_window && ui_user_sized && ui_keep_w >= 260 && ui_keep_h >= 160) {
            screen_width = ui_keep_w;           /* the size the user gave the window, whatever full screen did to screen_width since */
            screen_height = ui_keep_h;
        } else {
            screen_width = screen_height = 0;   /* window follows the next video's size */
        }
        startup_volume = 100;                   /* ffplay converts this each time; keep it fresh */
        input_filename = q_items[q_pos];        /* read_thread and the title use it */
        {                                       /* the window title: ffplay-custom - name, the name the title bar shows */
            static char ui_title[400];
            char nm[320];

            ui_q_name(q_pos, nm, sizeof(nm));
            snprintf(ui_title, sizeof(ui_title), "ffplay-custom - %s", nm);
            window_title = ui_title;
            if (window)
                SDL_SetWindowTitle(window, window_title);
        }
        if (xf_stream && xf_name == q_items[q_pos]) {
            /* it has been playing quietly under the end of the last item: carry on with it */
            is = xf_stream;
            xf_stream = NULL;
            xf_name = NULL;
            is->xf_gain = 1.0f;
        } else {
            ui_xf_abort();
            is = stream_open(q_items[q_pos], file_iformat);
            if (!is) {
                av_log(NULL, AV_LOG_FATAL, "Failed to initialize VideoState!\n");
                continue;                       /* skip it, try the next item */
            }
            if (ui_session_volume >= 0)
                is->audio_volume = ui_session_volume;
        }
        event_loop(is);                         /* returns when this item is over */
    }

    /* never returns */

    return 0;
}
