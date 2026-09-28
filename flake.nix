{
  description = "xray traffic poller + cli";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      packages.${system}.default = pkgs.rustPlatform.buildRustPackage {
        pname = "xcli";
        version = "0.2.0";
        src = self;
        cargoLock.lockFile = ./Cargo.lock;
        nativeBuildInputs = [ pkgs.protobuf ];
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [ cargo rustc rustfmt clippy rust-analyzer protobuf ];
      };
    };
}
