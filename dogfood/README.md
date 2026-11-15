# Dogfooding av Dunder

Det här är Dunder-program som kompileras och körs med Dunders egen backend.
De används också av kompilatorns integrationstester, med kontrollerad stdout
och definierade felstatusar. Importer skrivs utan filändelse.

Det fristående [Tabell-projektet](../tabell/README.md) använder också
Dunder för ett riktigt CSV-CLI med eget manifest, parser, gruppering och
diagnostik. Det driver importer utan citattecken, strängsortering och stderr.

Kör dogfood-testerna från reporoten:

```sh
dunder test dogfood/tests.ddr
```
program och deras tester går också att köra direkt:

```sh
dunder run dogfood/structs.ddr
dunder test dogfood/geometry.ddr
dunder test dogfood/parameter_cases.ddr
```

Med kompilatorn kopierad till `build/dunder` används samma kommandon som
`./build/dunder run ...` och `./build/dunder test ...`.

| Program | Vad det provar | Förväntade stdout-rader med `dunder run` |
| --- | --- | --- |
| [collections.ddr](collections.ddr) | Arrayändring, intervall, iteratorer och längd. | `-2`, `-1`, `0`, `1`, `13`, `3` |
| [recursion.ddr](recursion.ddr) | Rekursiv Fibonacci och Euklides algoritm. | `6765`, `21` |
| [sorting.ddr](sorting.ddr) | Insertion sort på en uttrycklig arrayklon, lånad parameter, for/while och ordningskontroll. | `45`, `9` |
| [iterators.ddr](iterators.ddr) | Fold med callback, uttryckligt klonad iteratorsnapshot, continue och returnerat intervall. | `36`, `20`, `0` |
| [arena/main.ddr](arena/main.ddr) | Bump-allokering, kapacitetsfel och rekursiv traversering över tre moduler. | `28` |
| [structs.ddr](structs.ddr) | Exporterad struct, uttryck som input, värdekopia och fältändring. | `25`, `32`, `3` |
| [numeric/main.ddr](numeric/main.ddr) | f32-vektor, kompenserad f64-summering och rotberäkning med callback. | `5.0`, `2.0`, `true` |
| [filesystem.ddr](filesystem.ddr) | Medföljande sys, UTF-8-fil, append, metadata, rename och städning. | `18`, `filesystem ok` |
| [enums.ddr](enums.ddr) | Namngivna värden, payloads, uttömmande match och nästlade Ok/Err. | `42`, `enums ok` |
| [standard.ddr](standard.ddr) | Word counter med map/set, dynamiska arrayer, text, byte, SHA-256 och decimalparser. | `4`, `6`, `stdlib ok` |
| [utf8.ddr](utf8.ddr) | UTF-8, byte/kodpunkter, ordräkning, strängretur och text i structar. | `bytes=25`, `runes=20`, `words=5`, `🌍 Hej världen` |
| [tokenizer.ddr](tokenizer.ddr) | UTF-8-ord, ASCII-skiljetecken och citerade strängar med escapes. | `fn\|hälsa\|(\|namn\|)\|{\|print\|(\|"Hej 🌍"\|)\|}` |
| [webgpu/main.ddr](webgpu/README.md) | Wasm och WebGPU med samma Dunder-vertexdata som Metal och Vulkan. | Renderad triangel i webbläsarens canvas. |
| [metal/triangle.ddr](metal/triangle.ddr) | Nativefönster, en gradienttriangel och en Dunder-skriven händelseloop. | `triangle frames=N` med `--frames N`; kräver grafisk session. |
| [metal/main.ddr](metal/main.ddr) | Metal-scen med moduler, enumtillstånd, animation, dragning och tangentkommandon. | `atlas frames=N` med `--frames N`; kräver grafisk session. |

[parameter_cases.ddr](parameter_cases.ddr) testar `(20) -> 4`, uttryck på
båda sidor, flera argument och genererade fall i en loop.
[geometry.ddr](geometry.ddr) testar structargument direkt och genom en lokal
bindning. De två filerna är bibliotek utan `main` och körs med `dunder test`.
[tests.ddr](tests.ddr) samlar importträdet och lägger till två modulsamspelstest.

```dunder
@test {
    (Point { x: 3, y: 4 }) -> 25
    (Point { x: 6 / 2, y: 2 + 2 }) -> 20 + 5
    point := Point { x: 3, y: 4 }
    length_squared(point) == 25
}
pub fn length_squared(p: Point) -> i32 {
    p.x * p.x + p.y * p.y
}
```

Varje kopplat block eller `@test fn` är en testgrupp som körs i en egen
nativeprocess. Bool-uttryck blir assertions. Första felet avbryter gruppen,
och runnern fortsätter med nästa. Tester från gemensamma importer körs en
gång. Testbyggen behöver ingen `main` och kör inte programmets `main`.
Standardtidsgränsen är fem sekunder per grupp; `--timeout-ms` ändrar den.

Vanliga funktionsparametrar lånar resursvärden för läsning under anropet.
Bindning, tilldelning och retur flyttar arrayer, strängar, iteratorer och
structar/enums som innehåller sådana värden. Använd `.clone()` när båda
ägarna ska finnas kvar. En parameter med `move` tar över värdet och anropas
med `move value` för en redan lagrad ägare. `mut` tillåter ändring;
`&mut value` ger funktionen ett exklusivt skrivlån. Tal och structar med
enbart kopierbara fält, som `geometry.Point`, kan fortsatt kopieras.

Vanlig `for` och `match` lånar också. `for value in values.iter()` lånar
arrayen under loopen. En lagrad ägande iterator kräver
`(move values).iter()` eller `values.clone().iter()`; det senare används
i iteratorprovet så att originalarrayen kan användas igen.
Arrayelement stöder `i32`, `i64`, `f32`, `f64`, `bool`, `string`, `rune`
och enums utan payload. Structfält kan också innehålla nästlade aggregat,
dynamiska arrayer och funktionsvärden.
En flytt av ett resursägande fält förbrukar hela ursprungsobjektet; övriga
fält städas fortfarande. Arrayelement kan tas ut med `pop` eller klonas
uttryckligen. Inline-arrayfält i C-layout klonas för en fristående ägare.
Användardefinierade iteratorer återstår.

Standardbiblioteket i `dunder` är Dunder-kod, inbäddad i
kompilatorn och importerad som `std.map`, `std.set` och så vidare.
`standard.ddr` kopplar ihop samlingarna i en UTF-8-ordräknare. Dess två
testgrupper och bibliotekens nio grupper körs med `tests.ddr`.
Kompilatorns lexer och typkontroll har egna tester i kärnrepot `dunder`.

[filesystem.ddr](filesystem.ddr) använder `import sys`, som är inbäddat i
kompilatorn. Programmet skapar en egen katalog med process-ID, provar
filflödet och städar de kända objekten. Det har två testgrupper, och sys
lägger till två grupper för felmeddelanden och typade felkoder.
Kör `dunder test dogfood/filesystem.ddr` för alla fyra.
`sys.read` ger `Ok(string)` / `Err(IoError)`; övriga resultat har `.ok` och
`.error`. Vanliga OS-fel hanteras i programmets kontrollflöde.

[enums.ddr](enums.ddr) har tre egna testgrupper för payload-utvärdering,
nästlade resultat och namngivna värden i arrayer och structfält. Med sys
blir det fem grupper: `dunder test dogfood/enums.ddr`.
Taggar och direkta grenar används utan vtables.

[numeric/math.ddr](numeric/math.ddr) testar vektorlängd, omskalad hypotenusa,
toleranser och kompenserad summering. [numeric/ode.ddr](numeric/ode.ddr)
integrerar en differentialekvation med Runge–Kutta och en typad callback.
Tillsammans med rotberäkning och precisionsprov i main finns sju numeriska
testgrupper. Kör `dunder test dogfood/numeric/main.ddr`.
Flyttalsutskriften är skriven i Dunder (`runtime/float.ddr`) och
kompileras in i program som skriver flyttal.

Grafikexemplen importerar vanliga källfiler relativt den importerande
filen. Från `metal/` leder `import ..graphics.macos as macos` till
[graphics/macos.ddr](graphics/macos.ddr). Från `vulkan/` leder
`import ..graphics.vulkan as vulkan` till [graphics/vulkan.ddr](graphics/vulkan.ddr).
Ett eget projekt kan lägga samma modulfiler och deras underkataloger i
`graphics/` bredvid sin `main.ddr` och använda `import graphics.macos as macos`
eller `import graphics.vulkan as vulkan`. Webbläsarexemplet använder en
separat [WebGPU-värd](webgpu/README.md) och delar triangeldatan med
nativeexemplen.

[metal/scene.ddr](metal/scene.ddr) och [metal/math.ddr](metal/math.ddr)
bygger Atlas-scenens geometri och animation. Fyra grupper i huvudträdet testar geometrihjälparnas
vertexlayout, scenens ändliga triangelista och återanvända lagring,
paus/palett/dragning samt sinus/cosinus i Dunder. De öppnar inget fönster.
`dunder test dogfood/metal/main.ddr` kör sju grupper inklusive delade sys-/
parse-tester.

[vulkan/main.ddr](vulkan/main.ddr) kör motsvarande Atlas-scen på Linux med
Vulkan. Geometri, animation och ASCII-kontroller är Dunder-kod. Headless-läge
och PPM-capture använder samma pipeline som fönsterläget. Fem nya grupper
provar geometri, scen, matematik och programargument utan grafikdrivrutin.

[text/scan.ddr](text/scan.ddr) implementerar `find`, `replace`, ordräkning,
UTF-8-gränser och avkodning i Dunder. Både textprogrammet och tokenizern
importerar samma modul; dess fyra testgrupper körs en gång i hela trädet.
Blanktecken är en uttryckligt listad delmängd. Tokenizern bevarar stavning
och citattecken, men är inte hela Dunder-lexern eller en fullständig
klassificering av Unicode-identifierare. Outslutna citat ger en assertion.

Strängmodellen lånar uppdelningen mellan byte och runes från
[V](https://docs.vlang.io/v-types.html#strings). `.len` räknar byte,
`.runes().len` räknar Unicode-kodpunkter och `s[a..b]` kräver UTF-8-gränser.
`.bytes()` och `.runes()` är vyer över oföränderlig text, inte allokerade
arrayer. En sammansatt emoji kan innehålla flera runes. Ingen normalisering
eller grapheme-klusterhantering görs.

Dynamiska strängar delar Dunders minnespool med arrayer och återvinns när
den sista ägaren släpps. En uttrycklig strängklon delar oföränderliga UTF-8-data
med referensräkning; en arrayklon har en oberoende buffert. Sammanslagning,
snitt och vissa `.str()`-anrop allokerar nya strängvärden. Gränsen för ett
enskilt strängblock i dessa operationer är 16 MiB, inklusive längdordet.

Arenan använder en fast `[i32; 96]` på stacken. `pool.reserve` kontrollerar
kapacitet och flyttar markören; den gamla markören är ett indexhandtag.
Varje trädnod upptar tre platser: värde, vänster index, höger index.
`-1` betyder tom länk. Det är fungerande bump-allokering inom den bufferten,
men inget allmänt allokerings-API. De rekursiva funktionerna lånar bufferten
för läsning, så traverseringen behöver inga arraykopior. Detta är ett
korrekthetsprov utan prestandaanspråk.
