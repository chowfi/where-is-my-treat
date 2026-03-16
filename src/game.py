# /// script
# requires-python = ">=3.11"
# dependencies = ["pygame-ce"]
# ///

import asyncio
import math
import pygame
import random

# When running inside RCade/Pyodide, main.js injects _get_input into globals
# before this script executes.  For local testing we provide a no-op fallback.
try:
    _get_input  # type: ignore[name-defined]
except NameError:

    def _get_input():
        return {
            "p1": {
                "up": False, "down": False, "left": False,
                "right": False, "a": False, "b": False,
            },
            "p2": {
                "up": False, "down": False, "left": False,
                "right": False, "a": False, "b": False,
            },
            "system": {"start_1p": False, "start_2p": False},
        }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 336, 262  # RCade display resolution
FPS = 60

COLOR_BG = (10, 10, 30)
COLOR_WHITE = (255, 255, 255)
COLOR_GREY = (150, 150, 150)

DIFFICULTY_SETTINGS = {
    #               speed_mult  swaps
    "EASY":        (1.0,         2),
    "MEDIUM":      (0.7,         4),
    "HARD":        (0.5,         6),
}
DIFFICULTY_NAMES = list(DIFFICULTY_SETTINGS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_and_scale(path, *, width=None, height=None):
    """Load an image and scale it so that *width* or *height* matches."""
    img = pygame.image.load(path).convert_alpha()
    if width:
        scale = width / img.get_width()
    elif height:
        scale = height / img.get_height()
    else:
        return img
    return pygame.transform.scale(
        img, (int(img.get_width() * scale), int(img.get_height() * scale))
    )


def _lerp(a, b, t):
    """Linear interpolation between a and b."""
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        random.seed(42)
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("where-is-my-treat")
        self.clock = pygame.time.Clock()
        self.running = True
        self.frame = 0

        # Detect whether we're running inside RCade (Pyodide) or locally.
        raw = _get_input()
        self.using_arcade_inputs = hasattr(raw, "to_py")

        # In RCade, main.js writes images to /game_assets on the Pyodide
        # virtual filesystem.  Locally they live in the assets/ folder.
        asset_dir = "/game_assets" if self.using_arcade_inputs else "assets"

        # -- Sprites ----------------------------------------------------------
        self.dog_frames = [
            _load_and_scale(f"{asset_dir}/dog.png", width=144),
            _load_and_scale(f"{asset_dir}/dog_tail_left.png", width=144),
            _load_and_scale(f"{asset_dir}/dog_tail_right.png", width=144),
        ]
        self.cup_image = _load_and_scale(f"{asset_dir}/cup.png", height=72)
        self.bagel_image = _load_and_scale(f"{asset_dir}/bagel.png", width=45)

        # -- Layout -----------------------------------------------------------
        cup_w = self.cup_image.get_width()
        cup_h = self.cup_image.get_height()
        cup_spacing = cup_w + 10
        cups_y = HEIGHT // 2 - cup_h - 30
        first_x = (WIDTH - (cup_spacing * 2 + cup_w)) // 2

        # Three fixed "slot" positions that never move (left / middle / right).
        self.slot_positions = [
            (first_x + i * cup_spacing, cups_y) for i in range(3)
        ]

        # cup_pos[cup_id] tracks the current on-screen (x, y) of each cup
        # (mutable list so animations can update it in place).
        self.cup_pos = [list(p) for p in self.slot_positions]

        # slot_to_cup[slot_index] → cup_id currently sitting at that slot.
        self.slot_to_cup = [0, 1, 2]

        # The bagel is always hidden under cup 0; this never changes mid-round.
        self.bagel_cup = 0

        # Centre the dog below the middle cup.
        dog_img = self.dog_frames[0]
        mid_x = self.slot_positions[1][0]
        self.dog_pos = (
            mid_x + cup_w // 2 - dog_img.get_width() // 2,
            HEIGHT - dog_img.get_height() - 12,
        )

        # -- Fonts ------------------------------------------------------------
        self.font_large = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        self.font_tiny = pygame.font.Font(None, 14)

        # -- Game state -------------------------------------------------------
        self.state = "title"
        self.score = 0
        self.message = ""
        self.highlight_slot = 1
        self.selected_slot = None
        self.reveal_timer = 0
        self.reveal_duration = FPS * 3 // 4

        # -- Shuffle / animation state ----------------------------------------
        self.shuffle_swaps = []
        self.current_shuffle_index = 0
        self.shuffle_timer = 0
        self.base_shuffle_duration = int(FPS * 1.5)
        self.shuffle_duration = self.base_shuffle_duration
        self.swap_cup_a = self.swap_cup_b = -1
        self.swap_start_a = self.swap_start_b = (0, 0)
        self.swap_end_a = self.swap_end_b = (0, 0)

        # -- Difficulty -------------------------------------------------------
        self.difficulty_index = 0
        self._apply_difficulty()

        # -- Edge-detection for button presses --------------------------------
        self._prev = {"up": False, "down": False, "left": False,
                      "right": False, "a": False}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _edge(self, key, pressed):
        """Return True on the frame a button goes from released → pressed."""
        triggered = pressed and not self._prev[key]
        self._prev[key] = pressed
        return triggered

    def _apply_difficulty(self):
        name = DIFFICULTY_NAMES[self.difficulty_index]
        speed_mult, swaps = DIFFICULTY_SETTINGS[name]
        self.shuffle_duration = max(5, int(self.base_shuffle_duration * speed_mult))
        self.swaps_per_round = swaps

    def _start_new_round(self):
        self.slot_to_cup = [0, 1, 2]
        for cid in range(3):
            self.cup_pos[cid] = list(self.slot_positions[cid])
        self.bagel_cup = 0
        self.highlight_slot = 1
        self.selected_slot = None
        self.reveal_timer = 0
        self.message = ""
        self.shuffle_swaps = []
        for _ in range(self.swaps_per_round):
            a = random.randint(0, 2)
            b = random.choice([x for x in range(3) if x != a])
            self.shuffle_swaps.append((a, b))
        self.current_shuffle_index = 0
        self.shuffle_timer = 0

    def _begin_swap(self, slot_a, slot_b):
        self.swap_cup_a = self.slot_to_cup[slot_a]
        self.swap_cup_b = self.slot_to_cup[slot_b]
        self.swap_start_a = tuple(self.slot_positions[slot_a])
        self.swap_start_b = tuple(self.slot_positions[slot_b])
        self.swap_end_a = tuple(self.slot_positions[slot_b])
        self.swap_end_b = tuple(self.slot_positions[slot_a])

    def _finish_swap(self, slot_a, slot_b):
        self.cup_pos[self.swap_cup_a] = list(self.swap_end_a)
        self.cup_pos[self.swap_cup_b] = list(self.swap_end_b)
        self.slot_to_cup[slot_a], self.slot_to_cup[slot_b] = (
            self.slot_to_cup[slot_b], self.slot_to_cup[slot_a],
        )

    # ------------------------------------------------------------------
    # Update (one frame of game logic)
    # ------------------------------------------------------------------
    def update(self, inputs):
        self.frame += 1
        p1 = inputs["p1"]

        # -- Title screen -----------------------------------------------------
        if self.state == "title":
            if self._edge("up", p1["up"]) and self.difficulty_index > 0:
                self.difficulty_index -= 1
                self.score = 0
                self._apply_difficulty()
            if self._edge("down", p1["down"]) and self.difficulty_index < len(DIFFICULTY_NAMES) - 1:
                self.difficulty_index += 1
                self.score = 0
                self._apply_difficulty()
            if inputs["system"]["start_1p"] or p1["a"]:
                self._start_new_round()
                self.state = "show_bagel"
            return

        # -- Show the bagel before covering -----------------------------------
        if self.state == "show_bagel":
            self.reveal_timer += 1
            if self.reveal_timer >= FPS:
                self.state = "cover"
                self.reveal_timer = 0
            return

        # -- Cover the bagel, then start shuffling ----------------------------
        if self.state == "cover":
            self.reveal_timer += 1
            if self.reveal_timer >= FPS // 2:
                self.state = "shuffle"
                self.shuffle_timer = 0
                if self.current_shuffle_index < len(self.shuffle_swaps):
                    self._begin_swap(*self.shuffle_swaps[self.current_shuffle_index])
            return

        # -- Animate cup swaps ------------------------------------------------
        if self.state == "shuffle":
            if self.current_shuffle_index >= len(self.shuffle_swaps):
                self.state = "choose"
                return
            self.shuffle_timer += 1
            t = min(1.0, self.shuffle_timer / max(1, self.shuffle_duration))
            for attr, start, end in [
                ("swap_cup_a", "swap_start_a", "swap_end_a"),
                ("swap_cup_b", "swap_start_b", "swap_end_b"),
            ]:
                cid = getattr(self, attr)
                s = getattr(self, start)
                e = getattr(self, end)
                self.cup_pos[cid][0] = _lerp(s[0], e[0], t)
                self.cup_pos[cid][1] = _lerp(s[1], e[1], t)
            if self.shuffle_timer >= self.shuffle_duration:
                self._finish_swap(*self.shuffle_swaps[self.current_shuffle_index])
                self.current_shuffle_index += 1
                self.shuffle_timer = 0
                if self.current_shuffle_index < len(self.shuffle_swaps):
                    self._begin_swap(*self.shuffle_swaps[self.current_shuffle_index])
            return

        # -- Player chooses a cup ---------------------------------------------
        if self.state == "choose":
            if self._edge("left", p1["left"]):
                self.highlight_slot = max(0, self.highlight_slot - 1)
            if self._edge("right", p1["right"]):
                self.highlight_slot = min(2, self.highlight_slot + 1)
            if self._edge("a", p1["a"]):
                self.selected_slot = self.highlight_slot
                self.state = "reveal"
                self.reveal_timer = 0
                if self.slot_to_cup[self.selected_slot] == self.bagel_cup:
                    self.message = "You found the bagel!"
                    self.score += 1
                else:
                    self.message = "No treat there!"
            return

        # -- Reveal result ----------------------------------------------------
        if self.state == "reveal":
            self.reveal_timer += 1
            if self.reveal_timer >= self.reveal_duration:
                self.state = "result"
            return

        # -- Auto-advance to next round ---------------------------------------
        if self.state == "result":
            self._start_new_round()
            self.state = "show_bagel"

    # ------------------------------------------------------------------
    # Draw (render one frame)
    # ------------------------------------------------------------------
    def draw(self):
        self.screen.fill(COLOR_BG)

        if self.state == "title":
            self._draw_title()
            pygame.display.flip()
            return

        self._draw_cups()
        self._draw_dog()
        self._draw_bagel()
        self._draw_selector()
        self._draw_hud()
        pygame.display.flip()

    def _draw_title(self):
        cx = WIDTH // 2
        cy = HEIGHT // 2
        lines = [
            (self.font_large, "Where Is My Treat?", cy - 40),
            (self.font_small, "1P START to begin",  cy - 10),
            (self.font_small, "A / D to move",      cy + 12),
            (self.font_small, "F to choose",         cy + 34),
        ]
        for font, text, y in lines:
            surf = font.render(text, True, COLOR_WHITE)
            self.screen.blit(surf, surf.get_rect(center=(cx, y)))

        # Difficulty selector
        label = self.font_tiny.render("Difficulty (W/S):", True, COLOR_GREY)
        self.screen.blit(label, label.get_rect(center=(cx, cy + 64)))
        for i, name in enumerate(DIFFICULTY_NAMES):
            color = COLOR_WHITE if i == self.difficulty_index else COLOR_GREY
            surf = self.font_tiny.render(name, True, color)
            self.screen.blit(surf, surf.get_rect(center=(cx, cy + 64 + (i + 1) * 20)))

    def _draw_cups(self):
        for cup_id in range(3):
            cx, cy = self.cup_pos[cup_id]
            lift = 0
            if self.state in ("reveal", "result") and self.selected_slot is not None:
                if self.slot_to_cup[self.selected_slot] == cup_id:
                    t = min(1.0, self.reveal_timer / max(1, self.reveal_duration))
                    lift = -int(20 * t)
            bob = int(math.sin(self.frame * 0.1 + cup_id * 0.4) * 4)
            self.screen.blit(self.cup_image, (cx, cy + lift + bob))

    def _draw_dog(self):
        idx = (self.frame // 20) % len(self.dog_frames)
        bob = int(math.sin(self.frame * 0.08) * 3)
        self.screen.blit(self.dog_frames[idx],
                         (self.dog_pos[0], self.dog_pos[1] + bob))

    def _draw_bagel(self):
        bx, by = self.cup_pos[self.bagel_cup]
        pos = (
            bx + (self.cup_image.get_width() - self.bagel_image.get_width()) // 2,
            by + self.cup_image.get_height() - self.bagel_image.get_height() // 3,
        )
        show = (
            self.state == "show_bagel"
            or (self.state in ("reveal", "result")
                and self.selected_slot is not None
                and self.slot_to_cup[self.selected_slot] == self.bagel_cup)
        )
        if show:
            self.screen.blit(self.bagel_image, pos)

    def _draw_selector(self):
        if self.state != "choose":
            return
        sx, sy = self.slot_positions[self.highlight_slot]
        pygame.draw.rect(self.screen, COLOR_WHITE,
                         (sx, sy - 6, self.cup_image.get_width(), 2))

    def _draw_hud(self):
        if self.state in ("reveal", "result") and self.message:
            surf = self.font_small.render(self.message, True, COLOR_WHITE)
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, 32)))
        score = self.font_small.render(f"Score: {self.score}", True, COLOR_WHITE)
        self.screen.blit(score, score.get_rect(bottomright=(WIDTH - 8, HEIGHT - 8)))

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    async def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

            # Read keyboard state (works both locally and in the browser).
            keys = pygame.key.get_pressed()
            kb = {
                "p1": {
                    "up": keys[pygame.K_UP] or keys[pygame.K_w],
                    "down": keys[pygame.K_DOWN] or keys[pygame.K_s],
                    "left": keys[pygame.K_LEFT] or keys[pygame.K_a],
                    "right": keys[pygame.K_RIGHT] or keys[pygame.K_d],
                    "a": keys[pygame.K_f],
                    "b": keys[pygame.K_x],
                },
                "p2": {
                    "up": False, "down": False, "left": False,
                    "right": False, "a": False, "b": False,
                },
                "system": {
                    "start_1p": keys[pygame.K_SPACE] or keys[pygame.K_RETURN],
                    "start_2p": False,
                },
            }

            # Merge arcade hardware input (if available) with keyboard.
            if self.using_arcade_inputs:
                arc = _get_input().to_py()
                inputs = {
                    "p1": {k: arc["p1"][k] or kb["p1"][k] for k in kb["p1"]},
                    "p2": arc["p2"],
                    "system": {k: arc["system"][k] or kb["system"][k] for k in kb["system"]},
                }
            else:
                inputs = kb

            self.update(inputs)
            self.draw()
            self.clock.tick(FPS)
            await asyncio.sleep(0)

        pygame.quit()


async def main():
    game = Game()
    await game.run()


# In Pyodide there is already a running event loop (the browser's), so we
# schedule onto it with ensure_future.  Locally no loop exists yet, so we
# fall back to asyncio.run().
try:
    asyncio.ensure_future(main())
except RuntimeError:
    asyncio.run(main())
