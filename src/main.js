import "./style.css";
import { loadPyodide } from "pyodide";
import { PLAYER_1, PLAYER_2, SYSTEM } from "@rcade/plugin-input-classic";
import gameCode from "./game.py?raw";
import wheels from "virtual:pyodide-wheels";

import dogUrl from "./assets/dog.png";
import dogTailLeftUrl from "./assets/dog_tail_left.png";
import dogTailRightUrl from "./assets/dog_tail_right.png";
import cupUrl from "./assets/cup.png";
import bagelUrl from "./assets/bagel.png";

async function loadAssetToFS(pyodide, url, fsPath) {
    const response = await fetch(url);
    const buffer = await response.arrayBuffer();
    pyodide.FS.writeFile(fsPath, new Uint8Array(buffer));
}

async function main() {
    const pyodide = await loadPyodide({
        indexURL: "/assets",
    });

    // Set up SDL2 canvas for pygame rendering
    const canvas = document.getElementById("canvas");
    pyodide.canvas.setCanvas2D(canvas);

    // Load micropip for installing local wheels
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");

    // Install all wheels from local assets
    for (const wheel of wheels) {
        await micropip.install(`/assets/${wheel}`);
    }

    // Pre-load image assets into Pyodide's virtual filesystem
    pyodide.FS.mkdir("/game_assets");
    await Promise.all([
        loadAssetToFS(pyodide, dogUrl, "/game_assets/dog.png"),
        loadAssetToFS(pyodide, dogTailLeftUrl, "/game_assets/dog_tail_left.png"),
        loadAssetToFS(pyodide, dogTailRightUrl, "/game_assets/dog_tail_right.png"),
        loadAssetToFS(pyodide, cupUrl, "/game_assets/cup.png"),
        loadAssetToFS(pyodide, bagelUrl, "/game_assets/bagel.png"),
    ]);

    // Create input bridge - called from Python
    const getInput = () => ({
        p1: {
            up: PLAYER_1.DPAD.up,
            down: PLAYER_1.DPAD.down,
            left: PLAYER_1.DPAD.left,
            right: PLAYER_1.DPAD.right,
            a: PLAYER_1.A,
            b: PLAYER_1.B,
        },
        p2: {
            up: PLAYER_2.DPAD.up,
            down: PLAYER_2.DPAD.down,
            left: PLAYER_2.DPAD.left,
            right: PLAYER_2.DPAD.right,
            a: PLAYER_2.A,
            b: PLAYER_2.B,
        },
        system: {
            start_1p: SYSTEM.ONE_PLAYER,
            start_2p: SYSTEM.TWO_PLAYER,
        },
    });

    pyodide.globals.set("_get_input", getInput);

    // Run the game
    await pyodide.runPythonAsync(gameCode);
}

main();
