#!/bin/sh
# RUSTC_WRAPPER shim: link std dynamically; rpath points at this user's toolchain libstd-*.so.
# rpath also has `$ORIGIN/deps` for the dependency-dylib approach. Only real crate compilations are touched (probes like `rustc -vV` pass through).
rustc=$1; shift
case " $* " in
  *" --crate-name "*) case " $* " in *" --crate-name ___ "*) ;; *)
    lib=$("$rustc" --print target-libdir)
    exec "$rustc" "$@" -Cprefer-dynamic "-Clink-arg=-Wl,-rpath,$lib,-rpath,\$ORIGIN/deps" ;;
  esac ;;
esac
exec "$rustc" "$@"
