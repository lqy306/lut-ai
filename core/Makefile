# Makefile — lut_eval C core library
.POSIX:

CC      = gcc
CFLAGS  = -std=c99 -O2 -fPIC -Wall -Wextra -Wno-unused-function -pedantic
LDFLAGS = -shared
LIBS    = -lm

# Object files
OBJS = stats.o local_eval.o

# Output
LIB = liblut_eval_core.so

all: $(LIB)

# ── Build shared library ─────────────────────────────────────────────────

$(LIB): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS) $(LIBS)

stats.o: stats.c lut_eval.h
	$(CC) $(CFLAGS) -c $< -o $@

local_eval.o: local_eval.c lut_eval.h
	$(CC) $(CFLAGS) -c $< -o $@

# ── Test (link with statically-compiled test if needed) ──────────────────

test: $(LIB)
	@echo "Library built: $(LIB)"
	@ls -la $(LIB)

# ── Clean ────────────────────────────────────────────────────────────────

clean:
	rm -f $(OBJS) $(LIB)

.PHONY: all clean test
