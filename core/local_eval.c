/*
 * local_eval.c — Local heuristic evaluation (ANSI C, BSD Allman style)
 *
 * Pure-formula scoring for LUT-processed images without AI.
 * Produces a score (30–95), style tags, and a short description.
 */

#include "lut_eval.h"

#include <math.h>
#include <string.h>
#include <stdio.h>

/* ── Clamp helper ──────────────────────────────────────────────────────── */

static float
clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* ── Local evaluation ──────────────────────────────────────────────────── */

void
local_evaluate(const color_stats_t *stats, local_eval_result_t *result)
{
    float intensity, score;
    int   warm_count, cool_count;

    char tag_buf[256];

    if (!stats || !result)
        return;

    /* ── Compute raw intensity ────────────────────────────────────────
     *
     *   intensity = |avg_s - 28| * 0.3
     *             + contrast     * 0.1
     *             + |warm_bias|  * 0.15
     *
     * Reference point: avg_s ≈ 28 is a typical "natural" saturation
     * level for well-balanced photos.
     */

    intensity = fabsf(stats->avg_s - 28.0f) * 0.3f
              + stats->contrast                * 0.1f
              + fabsf(stats->warm_bias)        * 0.15f;

    score = 50.0f + intensity;
    score = clampf(score, 30.0f, 95.0f);
    result->score = score;

    /* ── Determine tags ─────────────────────────────────────────────── */

    tag_buf[0] = '\0';
    warm_count = 0;
    cool_count = 0;

    /* Temperature tag */
    if (stats->warm_bias > 15.0f)
    {
        strcat(tag_buf, "温暖");
        warm_count++;
    }
    else if (stats->warm_bias < -15.0f)
    {
        strcat(tag_buf, "冷调");
        cool_count++;
    }
    else if (stats->warm_bias > 5.0f)
    {
        strcat(tag_buf, "中性偏暖");
        warm_count++;
    }
    else if (stats->warm_bias < -5.0f)
    {
        strcat(tag_buf, "中性偏冷");
        cool_count++;
    }
    else
    {
        strcat(tag_buf, "中性");
    }

    /* Saturation tag */
    if (stats->avg_s > 50.0f)
    {
        strcat(tag_buf, ",高饱和");
    }
    else if (stats->avg_s < 15.0f)
    {
        strcat(tag_buf, ",低饱和");
    }
    else
    {
        strcat(tag_buf, ",自然饱和");
    }

    /* Contrast tag */
    if (stats->contrast > 60.0f)
    {
        strcat(tag_buf, ",高对比");
    }
    else if (stats->contrast < 30.0f)
    {
        strcat(tag_buf, ",柔和");
    }
    else
    {
        strcat(tag_buf, ",适中对比");
    }

    strncpy(result->tags, tag_buf, sizeof(result->tags) - 1);
    result->tags[sizeof(result->tags) - 1] = '\0';

    /* ── Generate description ────────────────────────────────────────── */

    {
        char desc[512];
        const char *temp_word;
        const char *sat_word;
        const char *contrast_word;

        if (stats->warm_bias > 15.0f)
            temp_word = "暖调明显";
        else if (stats->warm_bias < -15.0f)
            temp_word = "冷调明显";
        else if (stats->warm_bias > 5.0f)
            temp_word = "轻微暖调";
        else if (stats->warm_bias < -5.0f)
            temp_word = "轻微冷调";
        else
            temp_word = "色温中性";

        if (stats->avg_s > 50.0f)
            sat_word = "色彩浓郁";
        else if (stats->avg_s < 15.0f)
            sat_word = "色彩清淡";
        else
            sat_word = "色彩自然";

        if (stats->contrast > 60.0f)
            contrast_word = "高对比度，画面锐利";
        else if (stats->contrast < 30.0f)
            contrast_word = "低对比度，画面柔和";
        else
            contrast_word = "对比度适中";

        snprintf(desc, sizeof(desc),
                 "%s，%s，%s。评分 %.0f/100。",
                 temp_word, sat_word, contrast_word, score);

        strncpy(result->description, desc, sizeof(result->description) - 1);
        result->description[sizeof(result->description) - 1] = '\0';
    }
}
