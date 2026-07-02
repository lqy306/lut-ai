/*
 * lut_eval.h — LUT evaluation core (ANSI C, BSD Allman style)
 *
 * Public API for color statistics extraction and local heuristic
 * evaluation of LUT-processed images.
 */

#ifndef LUT_EVAL_CORE_H
#define LUT_EVAL_CORE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Color statistics ──────────────────────────────────────────────────── */

typedef struct
{
    float avg_r;        /* RGB average (0–255)                             */
    float avg_g;
    float avg_b;
    float avg_h;        /* HSV average (H: 0–360, S/V: 0–100)             */
    float avg_s;
    float avg_v;
    float contrast;     /* Luminance standard deviation                    */
    float warm_bias;    /* (avg_r - avg_b) * (1 + avg_s / 200)            */
} color_stats_t;

/*
 * Extract color statistics from an RGB image buffer.
 *
 * Parameters:
 *   data  — tightly packed RGB pixel data (w × h × 3 bytes)
 *   w     — image width in pixels
 *   h     — image height in pixels
 *   stats — output structure
 *
 * Returns:
 *   0 on success, -1 on invalid input.
 */
int extract_stats(const uint8_t *data, int w, int h, color_stats_t *stats);

/*
 * Serialize color statistics to a human-readable string.
 *
 * Parameters:
 *   stats   — input statistics
 *   buf     — output buffer
 *   buf_size — output buffer size (must be >= 512)
 *
 * Returns:
 *   Number of bytes written (excluding null terminator).
 */
int stats_serialize(const color_stats_t *stats, char *buf, int buf_size);

/* ── Local heuristic evaluation ────────────────────────────────────────── */

typedef struct
{
    float score;            /* 30–95 heuristic score                        */
    char  tags[256];        /* Comma-separated style tags                   */
    char  description[512]; /* Short textual description                    */
} local_eval_result_t;

/*
 * Evaluate color statistics locally (no AI) using heuristic formulas.
 *
 * intensity = |avg_s - 28| * 0.3 + contrast * 0.1 + |warm_bias| * 0.15
 * score    = clamp(50 + intensity, 30, 95)
 *
 * Tags are determined by warm_bias sign, saturation level, and contrast.
 *
 * Parameters:
 *   stats  — input color statistics
 *   result — output evaluation (score, tags, description)
 */
void local_evaluate(const color_stats_t *stats, local_eval_result_t *result);

#ifdef __cplusplus
}
#endif

#endif /* LUT_EVAL_CORE_H */
