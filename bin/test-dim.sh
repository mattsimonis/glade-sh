#!/bin/bash
# ── Dim / faint text diagnostic ──────────────────────────────────────────────
# Run this inside a Glade terminal to see which dim/grey styles render correctly.
# Compare: if "dim" and "normal" lines look identical, dim is broken at that layer.

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Dim / Faint text diagnostic"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── 1. Basic dim attribute (SGR 2) ──
echo "── 1. SGR 2 (dim/faint) ──────────────────────────────────"
printf "  Normal:  \e[0mThe quick brown fox jumps over the lazy dog\e[0m\n"
printf "  Dim:     \e[2mThe quick brown fox jumps over the lazy dog\e[0m\n"
printf "  Bold:    \e[1mThe quick brown fox jumps over the lazy dog\e[0m\n"
printf "  BoldDim: \e[1;2mThe quick brown fox jumps over the lazy dog\e[0m\n"
echo ""

# ── 2. Bright black (color 90 — often used as "grey") ──
echo "── 2. Bright black / dark grey (SGR 90) ─────────────────"
printf "  Normal:      \e[0mThis is normal text\e[0m\n"
printf "  Color 90:    \e[90mThis is bright-black (dark grey)\e[0m\n"
printf "  Dim+90:      \e[2;90mThis is dim + bright-black\e[0m\n"
echo ""

# ── 3. Dim with each standard color ──
echo "── 3. Dim applied to each color ─────────────────────────"
for c in 30 31 32 33 34 35 36 37; do
    name=""
    case $c in
        30) name="black  " ;; 31) name="red    " ;; 32) name="green  " ;;
        33) name="yellow " ;; 34) name="blue   " ;; 35) name="magenta" ;;
        36) name="cyan   " ;; 37) name="white  " ;;
    esac
    printf "  ${name}  normal: \e[${c}m████\e[0m  dim: \e[2;${c}m████\e[0m\n"
done
echo ""

# ── 4. 256-color grey ramp (colors 232-255) ──
echo "── 4. 256-color grey ramp (232–255) ─────────────────────"
printf "  "
for i in $(seq 232 255); do
    printf "\e[48;5;${i}m  "
done
printf "\e[0m\n"
printf "  "
for i in $(seq 232 255); do
    printf "\e[38;5;${i}m██"
done
printf "\e[0m\n"
echo ""

# ── 5. Dim vs opacity test ──
echo "── 5. Side-by-side comparison ───────────────────────────"
printf "  \e[37mWhite normal\e[0m  vs  \e[2;37mWhite dim\e[0m  vs  \e[90mBright-black\e[0m\n"
printf "  \e[0mDefault normal\e[0m  vs  \e[2mDefault dim\e[0m\n"
echo ""

# ── 6. tmux info ──
echo "── 6. Environment ────────────────────────────────────────"
echo "  \$TERM = $TERM"
if command -v tmux &>/dev/null && tmux list-sessions &>/dev/null 2>&1; then
    echo "  tmux default-terminal = $(tmux show -gv default-terminal 2>/dev/null)"
    echo "  tmux terminal-overrides = $(tmux show -gv terminal-overrides 2>/dev/null)"
fi
echo "  infocmp dim cap:"
infocmp -1 2>/dev/null | grep -i 'dim\|mh=' || echo "    (not found)"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  If 'Normal' and 'Dim' lines look identical → dim is broken."
echo "  If color blocks in section 3 show no difference → dim is ignored."
echo "  Check section 6 for TERM / tmux settings."
echo "═══════════════════════════════════════════════════════════"
echo ""
