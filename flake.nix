{
  description = "langgraph-checkpoint-neo4j — Neo4j checkpointer for LangGraph (Python + TypeScript)";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        fhsEnv = pkgs.buildFHSEnv {
          name = "neo4j-checkpoint-dev";

          targetPkgs = pkgs':
            with pkgs'; [
              # ── Monorepo Workspace ──────────────────────────────────
              bun # Bun runtime + workspace orchestration + TS package

              # ── Python Package (packages/python) ────────────────────
              python312 # Python 3.12
              uv # Fast Python package manager
              ruff # Python linter + formatter

              # ── System Libraries ────────────────────────────────────
              zlib
              stdenv.cc.cc.lib
              openssl # SSL/TLS for neo4j driver

              # ── Neo4j (test infrastructure) ─────────────────────────
              docker
              docker-compose

              # ── Development Utilities ───────────────────────────────
              jq # JSON processor
              tree # Directory tree viewer
              lefthook # Git hooks manager

              # ── Version Control ─────────────────────────────────────
              git
              curl

              # ── Shells ──────────────────────────────────────────────
              zsh
              bash
            ];

          profile = ''
            echo ""
            echo "🔷 langgraph-checkpoint-neo4j — Development Environment"
            echo "═══════════════════════════════════════════════════════"
            echo ""

            # ── Core Tooling Versions ──
            echo "📦 Bun:        $(bun --version)"
            echo "🐍 Python:     $(python3 --version 2>&1 | cut -d' ' -f2)"
            echo "📎 uv:         $(uv --version 2>&1 | cut -d' ' -f2)"
            echo "🔍 Ruff:       $(ruff --version 2>&1 | cut -d' ' -f2)"
            echo ""

            # ── Bun version consistency check ──
            BUN_VERSION=$(bun --version)
            export BUN_VERSION
            bun run check:bun-version 2>/dev/null || true

            # ── Python Package Setup (packages/python) ──
            if [ -d "packages/python" ]; then
              if [ ! -d "packages/python/.venv" ]; then
                echo "🐍 Creating Python virtual environment in packages/python..."
                (cd packages/python && uv venv --python python3.12 --prompt "checkpoint-neo4j")
              fi

              if [ -d "packages/python/.venv" ]; then
                unset VIRTUAL_ENV
                source packages/python/.venv/bin/activate
                export PYTHONPATH="$PWD/packages/python/src:''${PYTHONPATH:-}"
                echo "✅ Python venv: activated (packages/python/.venv)"
              fi

              # Auto-sync Python deps if lockfile exists
              if [ -f "packages/python/uv.lock" ] && [ -d "packages/python/.venv" ]; then
                (cd packages/python && uv sync --quiet 2>/dev/null) && echo "✅ Python deps: synced" || echo "⚠️  Run 'cd packages/python && uv sync' manually"
              fi
            fi

            # ── Bun Workspace Setup ──
            if [ -f "package.json" ]; then
              if [ ! -d "node_modules" ]; then
                echo "📦 Installing bun workspace dependencies..."
                bun install --silent 2>/dev/null && echo "✅ Bun workspace: installed" || echo "⚠️  Run 'bun install' manually"
              else
                echo "✅ Bun workspace: ready"
              fi
            fi

            echo ""

            # ── Prevent wrong package managers ──
            alias pip='echo "❌ Use uv instead of pip! Run: uv add <package>" && false'
            alias pip3='echo "❌ Use uv instead of pip3! Run: uv add <package>" && false'
            alias pip-compile='echo "❌ Use uv instead of pip-compile! Run: uv lock" && false'
            npm() {
              case "$1" in
                login|whoami|logout|token) command npm "$@" ;;
                *) echo "❌ Use bun instead of npm! Run: bun install <package>" && return 1 ;;
              esac
            }
            alias yarn='echo "❌ Use bun instead of yarn! Run: bun install" && false'
            alias pnpm='echo "❌ Use bun instead of pnpm! Run: bun install" && false'

            echo "📚 Common Commands:"
            echo ""
            echo "  Monorepo (root):"
            echo "    bun install                  - Install all workspace deps"
            echo "    bun run test                 - Run all tests (Python + TS)"
            echo "    bun run lint                 - Lint all packages"
            echo "    bun run format:python        - Format Python code"
            echo ""
            echo "  Python (packages/python):"
            echo "    bun run test:python           - Run Python tests"
            echo "    bun run lint:python            - Lint Python code"
            echo "    cd packages/python && uv add <pkg>  - Add Python dependency"
            echo "    cd packages/python && uv sync       - Sync Python deps"
            echo ""
            echo "  TypeScript (packages/ts):"
            echo "    bun run test:ts               - Run TS tests"
            echo "    bun run lint:ts               - Type-check TS code"
            echo ""
            echo "  Neo4j:"
            echo "    bun run neo4j:up              - Start Neo4j (Docker)"
            echo "    bun run neo4j:down            - Stop Neo4j"
            echo "    open http://localhost:7474     - Neo4j Browser"
            echo ""
            echo "  Vendor submodules:"
            echo "    bun run submodule:update      - Update upstream LangGraph refs"
            echo ""
            echo "Ready to code! 🔷"
            echo ""
          '';

          runScript = "${pkgs.zsh}/bin/zsh";
        };
      in {
        devShells.default = pkgs.mkShell {
          shellHook = ''
            exec ${fhsEnv}/bin/neo4j-checkpoint-dev
          '';
        };
      }
    );
}
