import "./style.css";
import { loadPyodide } from "pyodide";
import { PLAYER_1, PLAYER_2, SYSTEM } from "@rcade/plugin-input-classic";
import gameCode from "./game.py?raw";
import wheels from "virtual:pyodide-wheels";

// Vite resolves these imports to hashed URLs at build time.
import dogUrl from "./assets/dog.png";
import dogTailLeftUrl from "./assets/dog_tail_left.png";
import dogTailRightUrl from "./assets/dog_tail_right.png";
import cupUrl from "./assets/cup.png";
import bagelUrl from "./assets/bagel.png";

const IMAGE_ASSETS = [
    [dogUrl,          "/game_assets/dog.png"],
    [dogTailLeftUrl,  "/game_assets/dog_tail_left.png"],
    [dogTailRightUrl, "/game_assets/dog_tail_right.png"],
    [cupUrl,          "/game_assets/cup.png"],
    [bagelUrl,        "/game_assets/bagel.png"],
];

async function loadAssetToFS(pyodide, url, fsPath) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
    const buffer = await response.arrayBuffer();
    pyodide.FS.writeFile(fsPath, new Uint8Array(buffer));
}

async function main() {
    const pyodide = await loadPyodide({ indexURL: "/assets" });

    pyodide.canvas.setCanvas2D(document.getElementById("canvas"));

    // Install Python wheels (pygame-ce and dependencies) from local assets.
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");
    for (const wheel of wheels) {
        await micropip.install(`/assets/${wheel}`);
    }

    // Fetch each image and write it into Pyodide's virtual filesystem so
    // that pygame.image.load() can find them by path.
    pyodide.FS.mkdir("/game_assets");
    await Promise.all(
        IMAGE_ASSETS.map(([url, path]) => loadAssetToFS(pyodide, url, path))
    );

    // Bridge RCade hardware inputs into Python.  The game polls this
    // function every frame via _get_input().to_py().
    pyodide.globals.set("_get_input", () => ({
        p1: {
            up: PLAYER_1.DPAD.up,    down: PLAYER_1.DPAD.down,
            left: PLAYER_1.DPAD.left, right: PLAYER_1.DPAD.right,
            a: PLAYER_1.A,            b: PLAYER_1.B,
        },
        p2: {
            up: PLAYER_2.DPAD.up,    down: PLAYER_2.DPAD.down,
            left: PLAYER_2.DPAD.left, right: PLAYER_2.DPAD.right,
            a: PLAYER_2.A,            b: PLAYER_2.B,
        },
        system: {
            start_1p: SYSTEM.ONE_PLAYER,
            start_2p: SYSTEM.TWO_PLAYER,
        },
    }));

    await pyodide.runPythonAsync(gameCode);
}

main().catch((err) => console.error("[game] FATAL:", err));
