{
  description = "lightweight xray subscription server";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};

    env = pkgs.python3.withPackages (ps: with ps; [
      fastapi
      uvicorn
      jinja2
    ]);
  in {
    packages.${system}.default = pkgs.writeShellScriptBin "xcli" ''
      export PATH="${pkgs.sops}/bin:$PATH"
      exec ${env}/bin/python ${self}/main.py "$@"
    '';
  };
}
