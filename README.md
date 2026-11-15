# Dunder Hundmat

Fristående program, exempel och integrationstester skrivna i Dunder. Här finns
större dogfood-program utanför språkets kärnrepo [`dunder`](https://github.com/Mik-pe/dunder):

- [`http/`](http/README.md) — en händelsestyrd, icke-blockerande HTTP/1.1-server byggd på `std.net.PollSet`, `StreamSet` och `std.fs.ReadDir` (`capability network, filesystem`).
- [`tabell/`](tabell/README.md) — CSV-verktyg för gruppering, summering och UTF-8-rapportsortering.
- [`dogfood/`](dogfood/README.md) — språk-, geometri-, arena-, flyttals-, Metal-, Vulkan- och WebGPU-exempel.

## Verifiering

Samtliga verifierings- och integrationsverktyg i `tools/` är skrivna i ren Dunder (`std.process`, `std.fs`, `std.json`, `std.net`). Kör hela sviten mot en byggd `dunder`-binär:

```sh
/sökväg/till/dunder run tools/verify.ddr -- /sökväg/till/dunder
```

För enstaka delar:

```sh
/sökväg/till/dunder test dogfood/tests.ddr
/sökväg/till/dunder test http/src/tests.ddr
/sökväg/till/dunder run tools/test_tabell.ddr -- /sökväg/till/dunder
/sökväg/till/dunder run tools/test_graphics.ddr -- /sökväg/till/dunder
/sökväg/till/dunder run tools/test_http.ddr -- /sökväg/till/dunder
```

Standardverifieringen kör funktionella prov utan prestandamätningar.
HTTP-provet kontrollerar bland annat 128 svar över åtta samtidiga klienter.
För en uttryckligt beställd throughputmätning finns ett separat opt-in-läge:

```sh
/sökväg/till/dunder run tools/test_http.ddr -- /sökväg/till/dunder --benchmark
```

Källorna använder `mut` för ändringsbara bindningar. Vanliga parametrar
lånar resursvärden, medan `move`-parametrar tar över ägaren. Se
[dogfood-programmens ägarregler](dogfood/README.md).
