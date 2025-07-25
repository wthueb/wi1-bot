{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs
          [
            "x86_64-linux"
            "aarch64-linux"
            "x86_64-darwin"
            "aarch64-darwin"
          ]
          (
            system:
            f rec {
              pkgs = nixpkgs.legacyPackages.${system};
              python = pkgs.python311;
            }
          );
    in
    {
      devShells = forAllSystems (
        { pkgs, python }:
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              mongosh
              uv
            ];
            env = {
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = python.interpreter;
            };
            shellHook = ''
              uv sync
              source .venv/bin/activate
            '';
          };
        }
      );
    };
}
