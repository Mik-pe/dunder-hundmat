# dunder-http

Lättvikts, single-process, händelsestyrd HTTP/1.1-server skriven i Dunder.

## Arkitektur

- `src/protocol.ddr`: zero-copy-parser för HTTP/1.1 och HTTP/1.0 över `rx_slab`-skivor (`Content-Length`, `Connection: keep-alive`/`close`, pipelining, storleksbegränsning samt avvisning av smuggling/`Transfer-Encoding`).
- `src/response.ddr`: direkt serialisering av HTTP-svar till `&mut []u8` med korrekt `HEAD`-beteende.
- `src/static.ddr`: katalogavgränsad filservering genom `std.fs.ReadDir`, `dir.resolve_read(rel)` och `file.read_bytes_limit(max_bytes)`.
- `src/server.ddr`: icke-blockerande `net.PollSet` + `net.StreamSet` händelseloop med SOA-tillstånd, lazy `rx_slab`, direkt skrivning från `tx_scratch` och `tx_arena`-backpressure över `POLLOUT`, samt idle timeout via `sys.now_ms()`.
- `src/main.ddr`: CLI (`--host`, `--port`, `--dir`, `--idle-ms`, `--max-requests`) deklarerad med `capability network, filesystem`.

## Bygg och kör

```sh
dunder test src/tests.ddr
dunder build -o build/dunder-http
./build/dunder-http --port 8080 --dir ./www
```

Från reporoten kör `dunder run tools/test_http.ddr -- /sökväg/till/dunder`
funktionella nätverksprov, inklusive 128 svar över åtta samtidiga klienter.
Mätningar av throughput och latens kräver den uttryckliga flaggan
`--benchmark` efter kompilatorsökvägen. Den vanliga verifieringen gör inga
sådana mätningar.

En tolkad begäran sparar fältens positioner i mottagningsbufferten.
`req.path(&rx_slab)`, `req.query(&rx_slab)`, `req.content_type(&rx_slab)` och
`req.body(&rx_slab)` returnerar läsvyer direkt in i bufferten. Servern kan
återanvända samma minne när den är färdig med vyerna.

Serverns buffertar och resursägande tillstånd flyttas vid bindning och retur.
Läsande hjälpfunktioner lånar sina parametrar; uppdateringar av parser,
sockettabeller och buffertar använder `&mut`.
`TcpStream`, `TcpListener` och `StreamSet` är unika resursägare som inte kan
klonas. `net.set_insert(&mut streams, move client)` lämnar över en anslutning
till sockettabellen. Stängning sker fortfarande uttryckligen, vanligtvis
genom `defer` och tabellens städfunktioner.
