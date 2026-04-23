{
  description = "xray subscription server";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
    python = pkgs.python3.withPackages (p: with p; [ fastapi uvicorn jinja2 pyyaml ]);
  in {
    packages.${system}.default = pkgs.writeShellScriptBin "xcli" ''
      exec ${python}/bin/python ${self}/main.py "$@"
    '';
  };
}
