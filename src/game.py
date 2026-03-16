# /// script
# requires-python = ">=3.11"
# dependencies = ["pygame-ce"]
# ///

import asyncio
import math
import pygame
import random

# Fallback input bridge so the game can run locally without RCade/JS.
try:
    _get_input  # type: ignore[name-defined]
except NameError:
    def _get_input():
        return {
            "p1": {
                "up": False,
                "down": False,
                "left": False,
                "right": False,
                "a": False,
                "b": False,
            },
            "p2": {
                "up": False,
                "down": False,
                "left": False,
                "right": False,
                "a": False,
                "b": False,
            },
            "system": {
                "start_1p": False,
                "start_2p": False,
            },
        }

# RCade game dimensions
WIDTH = 336
HEIGHT = 262
FPS = 60

# Colors
SKY = (10, 10, 30)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
GREY = (150, 150, 150)


class Game:
    def __init__(self):
        random.seed(42)
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("where-is-my-treat")
        self.clock = pygame.time.Clock()
        self.running = True
        self.frame = 0

        raw_inputs = _get_input()
        self.using_arcade_inputs = hasattr(raw_inputs, "to_py")

        asset_dir = "/game_assets" if self.using_arcade_inputs else "assets"

        self.dog_frames = [
            pygame.image.load(f"{asset_dir}/dog.png").convert_alpha(),
            pygame.image.load(f"{asset_dir}/dog_tail_left.png").convert_alpha(),
            pygame.image.load(f"{asset_dir}/dog_tail_right.png").convert_alpha(),
        ]
        self.cup_image = pygame.image.load(f"{asset_dir}/cup.png").convert_alpha()
        self.bagel_image = pygame.image.load(f"{asset_dir}/bagel.png").convert_alpha()

        target_cup_height = 72
        cup_scale = target_cup_height / self.cup_image.get_height()
        self.cup_image = pygame.transform.scale(
            self.cup_image,
            (int(self.cup_image.get_width() * cup_scale), target_cup_height),
        )

        target_dog_width = 144
        scaled_dog_frames = []
        for f in self.dog_frames:
            s = target_dog_width / f.get_width()
            scaled_dog_frames.append(
                pygame.transform.scale(f, (target_dog_width, int(f.get_height() * s)))
            )
        self.dog_frames = scaled_dog_frames

        target_bagel_width = 45
        bs = target_bagel_width / self.bagel_image.get_width()
        self.bagel_image = pygame.transform.scale(
            self.bagel_image,
            (target_bagel_width, int(self.bagel_image.get_height() * bs)),
        )

        # 3 fixed slot positions on screen (left, middle, right). These NEVER change.
        cups_y = HEIGHT // 2 - self.cup_image.get_height() - 30
        cup_spacing = self.cup_image.get_width() + 10
        first_x = (WIDTH - (cup_spacing * 2 + self.cup_image.get_width())) // 2
        self.slot_positions = [
            (first_x, cups_y),
            (first_x + cup_spacing, cups_y),
            (first_x + 2 * cup_spacing, cups_y),
        ]

        # Each cup has an ID (0, 1, 2) and a current screen position.
        # cup_pos[cup_id] = [x, y]  (mutable, for animation)
        self.cup_pos = [list(pos) for pos in self.slot_positions]

        # slot_to_cup[slot] = which cup ID is currently at that slot
        self.slot_to_cup = [0, 1, 2]

        # The bagel is ALWAYS under cup 0. This never changes during a round.
        self.bagel_cup = 0

        # Dog position
        mid_x, _ = self.slot_positions[1]
        dog_img = self.dog_frames[0]
        self.dog_pos = (
            mid_x + self.cup_image.get_width() // 2 - dog_img.get_width() // 2,
            HEIGHT - dog_img.get_height() - 12,
        )

        # Fonts
        self.font_large = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)

        # Game state
        self.state = "title"
        self.highlight_slot = 1
        self.selected_slot = None
        self.reveal_timer = 0
        # How long to show result before next round starts automatically
        self.reveal_duration = FPS // 4  # shorter, snappier rounds
        self.message = ""

        # Score
        self.score = 0

        # Shuffle state
        self.shuffle_swaps = []
        self.current_shuffle_index = 0
        self.shuffle_timer = 0
        # Base duration per swap; actual duration depends on difficulty.
        self.base_shuffle_duration = int(FPS * 1.5)
        self.shuffle_duration = self.base_shuffle_duration
        self.swap_cup_a = -1
        self.swap_cup_b = -1
        self.swap_start_a = (0, 0)
        self.swap_start_b = (0, 0)
        self.swap_end_a = (0, 0)
        self.swap_end_b = (0, 0)

        # Difficulty
        self.difficulties = ["EASY", "MEDIUM", "HARD"]
        self.difficulty_index = 0  # 0: easy, 1: medium, 2: hard

        # Input edge tracking for difficulty changes
        self.prev_up = False
        self.prev_down = False

        # Apply initial difficulty settings
        self._apply_difficulty()

    def _apply_difficulty(self):
        # Adjust shuffle speed based on difficulty.
        # EASY: current speed, MEDIUM: faster, HARD: fastest.
        speed_multipliers = [1.0, 0.7, 0.5]
        m = speed_multipliers[self.difficulty_index]
        self.shuffle_duration = max(5, int(self.base_shuffle_duration * m))

        # Also adjust how many swaps happen before the guess.
        # EASY: few swaps, HARD: many swaps.
        self.swaps_per_round = [2, 4, 6][self.difficulty_index]

    def _start_new_round(self):
        # Reset cups to their home slots.
        self.slot_to_cup = [0, 1, 2]
        for cup_id in range(3):
            slot = cup_id
            self.cup_pos[cup_id] = list(self.slot_positions[slot])

        # Bagel is always cup 0, which starts at slot 0 (left).
        self.bagel_cup = 0

        self.highlight_slot = 1
        self.selected_slot = None
        self.reveal_timer = 0
        self.message = ""

        # Generate random swap sequence (swap slots), count depends on difficulty.
        self.shuffle_swaps = []
        for _ in range(self.swaps_per_round):
            a = random.randint(0, 2)
            b = random.choice([x for x in range(3) if x != a])
            self.shuffle_swaps.append((a, b))

        self.current_shuffle_index = 0
        self.shuffle_timer = 0

    def _begin_swap_animation(self, slot_a, slot_b):
        """Set up the animation targets for swapping the cups at two slots."""
        self.swap_cup_a = self.slot_to_cup[slot_a]
        self.swap_cup_b = self.slot_to_cup[slot_b]
        self.swap_start_a = tuple(self.slot_positions[slot_a])
        self.swap_start_b = tuple(self.slot_positions[slot_b])
        self.swap_end_a = tuple(self.slot_positions[slot_b])
        self.swap_end_b = tuple(self.slot_positions[slot_a])

    def _finish_swap(self, slot_a, slot_b):
        """Finalize positions and update slot_to_cup after a swap completes."""
        self.cup_pos[self.swap_cup_a] = list(self.swap_end_a)
        self.cup_pos[self.swap_cup_b] = list(self.swap_end_b)
        self.slot_to_cup[slot_a], self.slot_to_cup[slot_b] = (
            self.slot_to_cup[slot_b],
            self.slot_to_cup[slot_a],
        )

    def update(self, inputs):
        self.frame += 1

        # Handle difficulty changes with W/S (up/down) - edge-triggered.
        # Only allowed from the title screen so gameplay isn't interrupted.
        up_pressed = inputs["p1"]["up"]
        down_pressed = inputs["p1"]["down"]
        if self.state == "title":
            difficulty_changed = False
            if up_pressed and not self.prev_up:
                if self.difficulty_index > 0:
                    self.difficulty_index -= 1
                    difficulty_changed = True
            if down_pressed and not self.prev_down:
                if self.difficulty_index < len(self.difficulties) - 1:
                    self.difficulty_index += 1
                    difficulty_changed = True

            if difficulty_changed:
                # Reset score and reapply difficulty when mode changes.
                self.score = 0
                self._apply_difficulty()

        self.prev_up = up_pressed
        self.prev_down = down_pressed

        if self.state == "title":
            if inputs["system"]["start_1p"] or inputs["p1"]["a"]:
                self._start_new_round()
                self.state = "show_bagel"
            return

        if self.state == "show_bagel":
            self.reveal_timer += 1
            if self.reveal_timer >= FPS:
                self.state = "cover"
                self.reveal_timer = 0
            return

        if self.state == "cover":
            self.reveal_timer += 1
            if self.reveal_timer >= FPS // 2:
                self.state = "shuffle"
                self.shuffle_timer = 0
                if self.current_shuffle_index < len(self.shuffle_swaps):
                    a, b = self.shuffle_swaps[self.current_shuffle_index]
                    self._begin_swap_animation(a, b)
            return

        if self.state == "shuffle":
            if self.current_shuffle_index >= len(self.shuffle_swaps):
                self.state = "choose"
                return

            self.shuffle_timer += 1
            t = min(1.0, self.shuffle_timer / max(1, self.shuffle_duration))

            # Animate: slide the two cups toward their targets.
            self.cup_pos[self.swap_cup_a][0] = self.swap_start_a[0] + (self.swap_end_a[0] - self.swap_start_a[0]) * t
            self.cup_pos[self.swap_cup_a][1] = self.swap_start_a[1] + (self.swap_end_a[1] - self.swap_start_a[1]) * t
            self.cup_pos[self.swap_cup_b][0] = self.swap_start_b[0] + (self.swap_end_b[0] - self.swap_start_b[0]) * t
            self.cup_pos[self.swap_cup_b][1] = self.swap_start_b[1] + (self.swap_end_b[1] - self.swap_start_b[1]) * t

            if self.shuffle_timer >= self.shuffle_duration:
                a, b = self.shuffle_swaps[self.current_shuffle_index]
                self._finish_swap(a, b)
                self.current_shuffle_index += 1
                self.shuffle_timer = 0
                if self.current_shuffle_index < len(self.shuffle_swaps):
                    a2, b2 = self.shuffle_swaps[self.current_shuffle_index]
                    self._begin_swap_animation(a2, b2)
            return

        if self.state == "choose":
            if inputs["p1"]["left"]:
                self.highlight_slot = max(0, self.highlight_slot - 1)
            if inputs["p1"]["right"]:
                self.highlight_slot = min(2, self.highlight_slot + 1)
            if inputs["p1"]["a"]:
                self.selected_slot = self.highlight_slot
                self.state = "reveal"
                self.reveal_timer = 0
                if self.slot_to_cup[self.selected_slot] == self.bagel_cup:
                    self.message = "You found the bagel!"
                    self.score += 1
                else:
                    self.message = "No treat there!"
            return

        if self.state == "reveal":
            self.reveal_timer += 1
            if self.reveal_timer >= self.reveal_duration:
                self.state = "result"
            return

        if self.state == "result":
            # Immediately advance to the next round without requiring input.
            self._start_new_round()
            self.state = "show_bagel"

    def draw(self, inputs):
        # Solid dark navy background
        self.screen.fill(SKY)

        if self.state == "title":
            t1 = self.font_large.render("Where Is My Treat?", True, WHITE)
            t2 = self.font_small.render("1P START to begin", True, WHITE)
            t3 = self.font_small.render("A / D to move", True, WHITE)
            t4 = self.font_small.render("F to choose", True, WHITE)
            self.screen.blit(t1, t1.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40)))
            self.screen.blit(t2, t2.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 10)))
            self.screen.blit(t3, t3.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 12)))
            self.screen.blit(t4, t4.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 34)))

            # Difficulty list on title screen, under the instructions.
            diff_label = self.font_small.render("Difficulty (W/S):", True, WHITE)
            self.screen.blit(
                diff_label,
                diff_label.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 64)),
            )
            for i, name in enumerate(self.difficulties):
                color = WHITE if i == self.difficulty_index else GREY
                text = self.font_small.render(name, True, color)
                self.screen.blit(
                    text,
                    text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 64 + (i + 1) * 20)),
                )

            pygame.display.flip()
            return

        # Draw each cup at its current animated position.
        for cup_id in range(3):
            cx, cy = self.cup_pos[cup_id]
            offset_y = 0

            # Lift animation on reveal
            if self.state in ("reveal", "result") and self.selected_slot is not None:
                if self.slot_to_cup[self.selected_slot] == cup_id:
                    t = min(1.0, self.reveal_timer / max(1, self.reveal_duration))
                    offset_y = -int(20 * t)

            bob = int(math.sin(self.frame * 0.1 + cup_id * 0.4) * 4)
            self.screen.blit(self.cup_image, (cx, cy + offset_y + bob))

        # Dog with tail wag
        dog_idx = (self.frame // 20) % len(self.dog_frames)
        dog_img = self.dog_frames[dog_idx]
        dog_bob = int(math.sin(self.frame * 0.08) * 3)
        self.screen.blit(dog_img, (self.dog_pos[0], self.dog_pos[1] + dog_bob))

        # Bagel visibility
        bagel_cup_x, bagel_cup_y = self.cup_pos[self.bagel_cup]
        bagel_draw_pos = (
            bagel_cup_x + (self.cup_image.get_width() - self.bagel_image.get_width()) // 2,
            bagel_cup_y + self.cup_image.get_height() - self.bagel_image.get_height() // 3,
        )
        if self.state == "show_bagel":
            self.screen.blit(self.bagel_image, bagel_draw_pos)
        elif self.state in ("reveal", "result"):
            if self.selected_slot is not None and self.slot_to_cup[self.selected_slot] == self.bagel_cup:
                self.screen.blit(self.bagel_image, bagel_draw_pos)

        # Selector
        if self.state == "choose":
            sx, sy = self.slot_positions[self.highlight_slot]
            pulse = 2 + int((math.sin(self.frame * 0.15) + 1) * 1.5)
            rect = pygame.Rect(sx, sy + self.cup_image.get_height() + 4, self.cup_image.get_width(), pulse)
            pygame.draw.rect(self.screen, WHITE, rect)

        # Result text
        if self.state in ("reveal", "result") and self.message:
            msg = self.font_small.render(self.message, True, WHITE)
            self.screen.blit(msg, msg.get_rect(center=(WIDTH // 2, 32)))

        # Score (bottom-right corner)
        score_text = self.font_small.render(f"Score: {self.score}", True, WHITE)
        score_rect = score_text.get_rect(bottomright=(WIDTH - 8, HEIGHT - 8))
        self.screen.blit(score_text, score_rect)

        pygame.display.flip()

    async def run(self):
        print("[py] game loop starting", flush=True)
        loop_count = 0
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
            if self.using_arcade_inputs:
                raw = _get_input()
                inputs = raw.to_py()
            else:
                keys = pygame.key.get_pressed()
                inputs = {
                    "p1": {
                        "up": keys[pygame.K_UP] or keys[pygame.K_w],
                        "down": keys[pygame.K_DOWN] or keys[pygame.K_s],
                        "left": keys[pygame.K_LEFT],
                        "right": keys[pygame.K_RIGHT],
                        "a": keys[pygame.K_z],
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

            self.update(inputs)
            self.draw(inputs)
            loop_count += 1
            if loop_count <= 3:
                print(f"[py] frame {loop_count}, state={self.state}", flush=True)
            self.clock.tick(FPS)
            await asyncio.sleep(0)

        pygame.quit()


async def main():
    game = Game()
    await game.run()


asyncio.run(main())
