/*
 * stats.c — Color statistics extraction (ANSI C, BSD Allman style)
 *
 * Extracts 8 color features from an RGB image buffer:
 *   avg_r, avg_g, avg_b, avg_h, avg_s, avg_v, contrast, warm_bias
 *
 * All operations are pure math — no external dependencies beyond <math.h>.
 */

#include "lut_eval.h"

#include <math.h>
#include <string.h>
#include <stdio.h>

/* ── Constants ─────────────────────────────────────────────────────────── */

#define STATS_SERIALIZE_BUF_MIN 512

/* ── RGB → HSV conversion ─────────────────────────────────────────────── */

/*
 * Convert a single RGB triplet (0–255) to HSV.
 * H: 0–360, S: 0–100, V: 0–100.
 */
static void
rgb_to_hsv(int r, int g, int b,
           float *h, float *s, float *v)
{
    float rf, gf, bf;
    float max, min, delta;

    rf = (float)r / 255.0f;
    gf = (float)g / 255.0f;
    bf = (float)b / 255.0f;

    max = rf;
    if (gf > max) max = gf;
    if (bf > max) max = bf;

    min = rf;
    if (gf < min) min = gf;
    if (bf < min) min = bf;

    delta = max - min;

    /* Value */
    *v = max * 100.0f;

    /* Saturation */
    if (max < 0.0001f)
    {
        *s = 0.0f;
        *h = 0.0f;
        return;
    }
    *s = (delta / max) * 100.0f;

    /* Hue */
    if (delta < 0.0001f)
    {
        *h = 0.0f;
        return;
    }

    if (max == rf)
    {
        *h = 60.0f * fmodf((gf - bf) / delta, 6.0f);
    }
    else if (max == gf)
    {
        *h = 60.0f * ((bf - rf) / delta + 2.0f);
    }
    else
    {
        *h = 60.0f * ((rf - gf) / delta + 4.0f);
    }

    if (*h < 0.0f)
        *h += 360.0f;
}

/* ── RGB → luminance (Rec. 709) ───────────────────────────────────────── */

/*
 * Convert an sRGB triplet to relative luminance using Rec. 709 coefficients.
 * L = 0.2126*R + 0.7152*G + 0.0722*B
 */
static float
rgb_to_luminance(int r, int g, int b)
{
    return 0.2126f * (float)r
         + 0.7152f * (float)g
         + 0.0722f * (float)b;
}

/* ── Extract statistics ────────────────────────────────────────────────── */

int
extract_stats(const uint8_t *data, int w, int h, color_stats_t *stats)
{
    int     i, n;
    double  sum_r, sum_g, sum_b;
    double  sum_h, sum_s, sum_v;
    double  sum_lum, sum_lum_sq;
    double  avg_lum;

    if (!data || w < 1 || h < 1 || !stats)
        return -1;

    n = w * h;

    sum_r = sum_g = sum_b = 0.0;
    sum_h = sum_s = sum_v = 0.0;
    sum_lum = sum_lum_sq = 0.0;

    for (i = 0; i < n; i++)
    {
        int r, g, b;
        float h_val, s_val, v_val;
        float lum;

        r = (int)data[i * 3];
        g = (int)data[i * 3 + 1];
        b = (int)data[i * 3 + 2];

        /* Accumulate RGB sums */
        sum_r += (double)r;
        sum_g += (double)g;
        sum_b += (double)b;

        /* RGB → HSV */
        rgb_to_hsv(r, g, b, &h_val, &s_val, &v_val);
        sum_h += (double)h_val;
        sum_s += (double)s_val;
        sum_v += (double)v_val;

        /* Luminance for contrast */
        lum = rgb_to_luminance(r, g, b);
        sum_lum    += (double)lum;
        sum_lum_sq += (double)lum * (double)lum;
    }

    /* Compute averages */
    {
        double inv_n;

        inv_n = 1.0 / (double)n;

        stats->avg_r = (float)(sum_r * inv_n);
        stats->avg_g = (float)(sum_g * inv_n);
        stats->avg_b = (float)(sum_b * inv_n);
        stats->avg_h = (float)(sum_h * inv_n);
        stats->avg_s = (float)(sum_s * inv_n);
        stats->avg_v = (float)(sum_v * inv_n);

        avg_lum = sum_lum * inv_n;
        stats->contrast = (float)sqrt((sum_lum_sq * inv_n)
                                      - (avg_lum * avg_lum));

        /* Warm bias: positive = warm, negative = cool */
        stats->warm_bias = (stats->avg_r - stats->avg_b)
                           * (1.0f + stats->avg_s / 200.0f);
    }

    return 0;
}

/* ── Serialize statistics ──────────────────────────────────────────────── */

int
stats_serialize(const color_stats_t *stats, char *buf, int buf_size)
{
    if (!stats || !buf || buf_size < STATS_SERIALIZE_BUF_MIN)
        return -1;

    return snprintf(buf, (size_t)buf_size,
        "RGB avg:     %.1f %.1f %.1f\n"
        "HSV avg:     %.1f %.1f %.1f\n"
        "Contrast:    %.2f\n"
        "Warm bias:   %+.2f  (%s)\n",
        stats->avg_r, stats->avg_g, stats->avg_b,
        stats->avg_h, stats->avg_s, stats->avg_v,
        stats->contrast,
        stats->warm_bias,
        stats->warm_bias > 0.0f ? "warm" : "cool");
}
