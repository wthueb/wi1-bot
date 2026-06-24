{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ flake-parts, treefmt-nix, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ treefmt-nix.flakeModule ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      perSystem =
        { pkgs, ... }:
        {
          devShells.default = pkgs.mkShell {
            packages = with pkgs; [
              ffmpeg-full
              uv
            ];
            shellHook = ''
              uv sync
              source .venv/bin/activate
            '';
          };

          treefmt = {
            projectRootFile = "flake.nix";

            programs.nixfmt.enable = true;
            programs.ruff-check.enable = true;
            programs.ruff-format.enable = true;
          };
        };
    };
}
