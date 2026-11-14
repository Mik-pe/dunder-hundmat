# Dunder Hundmat

Fristående program, exempel och integrationstester skrivna i Dunder. Här finns
större dogfood-program utanför språkets kärnrepo [`dunder`](https://github.com/Mik-pe/dunder):

- [`http/`](http/README.md) — en händelsestyrd, icke-blockerande HTTP/1.1-server byggd på `std.net.PollSet`, `StreamSet` och `std.fs.ReadDir` (`capability network, filesystem`).
- [`tabell/`](tabell/README.md) — CSV-verktyg för gruppering, summering och UTF-8-rapportsortering.
- [`dogfood/`](dogfood/README.md) — språk-, geometri-, arena-, flyttals-, Metal-, Vulkan- och WebGPU-exempel.

## Verifiering

Kör samtliga tester och serverns integrations-/lastsvit mot en byggd `dunder`-binär:

```sh
python3 tools/verify.py /sökväg/till/dunder
```

För enstaka delar:

```sh
/sökväg/till/dunder test dogfood/tests.ddr
/sökväg/till/dunder test http/src/tests.ddr
python3 tools/test-tabell.py /sökväg/till/dunder
python3 tools/test-graphics.py /sökväg/till/dunder
python3 tools/test-http.py /sökväg/till/dunder
```
