# dunder-http

Lättvikts, single-process, händelsestyrd HTTP/1.1-server skriven i Dunder.

## Arkitektur

- `src/protocol.ddr`: zero-copy-parser för HTTP/1.1 och HTTP/1.0 över `rx_slab`-skivor (`Content-Length`, `Connection: keep-alive`/`close`, pipelining, storleksbegränsning samt avvisning av smuggling/`Transfer-Encoding`).
- `src/response.ddr`: direkt serialisering av HTTP-svar till `&mut []u8` med korrekt `HEAD`-beteende.
- `src/static.ddr`: katalogavgränsad filservering genom `std.fs.ReadDir` + `fs.resolve_read` och `fs.read_bytes_limit`.
- `src/server.ddr`: icke-blockerande `net.PollSet` + `net.StreamSet` händelseloop med SOA-tillstånd, lazy `rx_slab`, direkt skrivning från `tx_scratch` och `tx_arena`-backpressure över `POLLOUT`, samt idle timeout via `sys.now_ms()`.
- `src/main.ddr`: CLI (`--host`, `--port`, `--dir`, `--idle-ms`, `--max-requests`) deklarerad med `capability network, filesystem`.

## Bygg och kör

```sh
dunder test src/tests.ddr
dunder build -o build/dunder-http
./build/dunder-http --port 8080 --dir ./www
```
