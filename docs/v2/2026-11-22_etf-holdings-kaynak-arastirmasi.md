# ETF holdings kaynakları — ölçülmüş araştırma (22 Kasım 2026)

Soru: UW gidince (#1283, abonelik 9 Ara) ETF holdings nereden gelecek? #354 ring-1 kümesi (133 fon,
25 M USD ADV tabanı) üzerinden ölçüldü. Hepsi salt-okunur; kayıt, ödeme, yeni anahtar yok.

## 1. Bugün elimizde olan

| Kaynak | Ring-1'den kaç fon | Not |
|---|---|---|
| Kendi ihraççı dosyalarımız (SSGA 21 + iShares 10) | **26** | günlük, anahtarsız, çalışıyor |
| Unusual Whales | **14** | 9 Aralık'ta gidiyor, 250 satır sınırı |
| Hiç günlük kaynağı olmayan | **93** | şu an üç aylık `sec/nport` Parquet'inden okunuyor |

Ölçüm: `rcdata/build/spine/etf_holdings.py` (SSGA_FUNDS, ISHARES_PRODUCTS, UW_FUNDS) ∩ #354 ring-1 listesi.

## 2. TickerInside (tickerinside.com) — ölçüldü

- **Kapsama: 133/133.** 76'sı ihraççının kendi dosyasından **günlük**, 56'sı SEC N-PORT, 1'i (AMLP) multi-asset.
- **Günlük okunan ihraççılar sadece üç:** iShares, State Street SPDR, **Global X** (`funds_by_source.issuer_files = 472`).
  VanEck, First Trust, WisdomTree, Invesco, Vanguard, Fidelity, Schwab günlük değil → N-PORT.
- **Tazelik (günlük katman):** dosya tarihleri 2026-11-19, site verisi 2026-11-20. Bir gün gecikme.
- **Tazelik (N-PORT katmanı) — en önemli bulgu:** her fonun **en yeni EDGAR dosyasını** okuyor.
  Ring-1'in N-PORT'tan gelen 57 fonunun rapor tarihleri: 2026-06-30 (21), 07-31 (15), **08-31 (17), 09-30 (4)**.
  Bizim elimizdeki toplu `2026q3_nport.zip` ise sadece 29 May – 31 Tem 2026 dönemlerini taşıyor.
  Yani **aynı veri bizde 2 ay daha eski** ve 2026q4 zip'i (≈Ocak 2027) gelene kadar daha da eskiyecek.
  Örnek: SMH, dönem 2026-09-30, EDGAR'a 2026-11-17'de düşmüş; bizim store'da en iyi hali 2026-07-31.
- **Tarihçe:** `/api/v1/history/{t}/{date}.json` → 2019'dan beri her çeyrek için **tüm pozisyonlar** (sadece ağırlık,
  adet yok). Günlük dosya arşivi 2026-09-03'te başlamış (22.551 snapshot).
- **Erişim:** anahtarsız, hesapsız, kota yok. `https://tickerinside.com/api/v1/fund/<ticker>.json` (fon başına bir GET,
  tüm pozisyonlar ağırlıklarıyla), `batch?funds=a,b,c`, `funds.json` (tek istekte 5.552 fonun katmanı + rapor tarihi),
  `universe.json`. Gece 22:00 UTC'den itibaren kuruluyor, 02:00 UTC'de bitiyor; 5 dk cache, ETag/304. robots.txt serbest.
- **Lisans:** anlık veriler + hesaplanan figürler **CC BY 4.0**. Açıkça izinli: "**her gecenin kopyasını saklamak, kendi
  serini kurmak dahil**". Şart: figürü gösterdiğin yerde TickerInside'a link. Tarihçe ve flows CC BY değil
  (`/legal/#history`): istek başına serbest ama **arşivi toplu çekmek / programlı biriktirmek yasak**.
  CUSIP/ISIN **servis etmiyor** (lisanslı kod), fonlar ve hisseler ticker ile anahtarlı.
- **Yasal risk:** düşük. Pozisyonlar ihraççının kendi yayınladığı veri + kamuya açık SEC dosyaları; site toplu ticari
  yeniden kullanım için ihraççının şartlarına bakmayı söylüyor.

## 3. Alpaca — hayır (ölçüldü)

Alpaca'nın tüm dokümantasyon indeksi (`https://docs.alpaca.markets/llms.txt`, 176 KB, her reference sayfası) çekildi:
**ETF holdings / constituents ucu yok.** "holdings" geçen tek yer hesap pozisyonları ve partner raporlama uçları.
Market Data API = hisse/kripto/opsiyon/haber/corporate actions. Elimizdeki anahtar bu iş için işe yaramıyor.

## 4. İhraççı siteleri — canlı denendi (bulut IP'sinden)

| İhraççı | Sonuç | Not |
|---|---|---|
| iShares | **200, CSV** | `/us/products/<id>/<slug>/latest-holdings.csv` — her iShares fonu için anahtarsız çalışıyor (IYW, EWZ denendi). Bizde sadece 10 fon tanımlı; ürün id'si ile **tüm iShares ailesi** eklenebilir. |
| SSGA SPDR | **200, xlsx** | mevcut yol çalışıyor |
| ARK | **200, CSV** | ARKK dosyası 2026-11-20 tarihli, çalışıyor |
| First Trust | 200, HTML | holdings tablosu HTML içinde var (FDN'de AMZN/META görüldü) → ayrıştırılabilir ama CSV yok |
| Invesco | 406 / sonsuz yönlendirme | CDN engeli |
| VanEck | 302 → 404 | CSV ucu bulunamadı |
| Global X | 403 / 429 | CDN engeli (bulut IP'si) |
| WisdomTree | 403 | daha önce de UA reddetmişti (30 Eki ölçümü) |
| Schwab | 403 Access Denied | |
| Vanguard | 404 | eski JSON ucu kapanmış |

**Uyarı:** bu 403/406'lar bulut konteynerinin IP'si olabilir; homesrv'den sonuç farklı çıkabilir. Ama repodaki
30 Eki ölçümü de aynı yöne işaret ediyor (First Trust ASP.NET postback, WisdomTree UA reddi, Invesco 500).

## 5. Ücretli / diğer API'ler

| Sağlayıcı | ETF holdings | Fiyat | Karar |
|---|---|---|---|
| FMP | var, ama **sadece Ultimate** | 139 $/ay (yıllık 99 $/ay) | gereksiz: TickerInside bedava aynı işi yapıyor |
| EODHD | Fundamentals planında | 59,99 $/ay; **ticari kullanım 399 $/ay'dan başlıyor** | hayır |
| Polygon (artık "Massive") | ETF Global ortağı üzerinden constituents | plana bağlı, fiyat açık değil | hayır |
| Tiingo | belgelenmiş holdings ucu bulunamadı | — | hayır |
| Intrinio | var (`/etfs/{id}/holdings`) | kurumsal | hayır |
| etf.com / ETFdb (VettaFi) | public API yok | — | Cloudflare 403, API yok |
| stockanalysis.com | sayfa var, API/lisans yok | — | kazıma, lisans yok → yasal risk |

## 6. Fincept (FinceptTerminal) — yeni bir şey yok

GitHub kod aramasıyla bakıldı (`repo:Fincept-Corporation/FinceptTerminal etf_holdings`, 4 isabet):
ETF holdings'i **FMP**'den (`fincept-qt/scripts/fmp_data.py:460 get_etf_holdings`, `FMP_API_KEY` şart) ve
**OpenBB**'den (`openbb_data.py:48 api/v1/etf/holdings?provider=fmp`, `OPENBB_API_KEY` şart) alıyor.
Yani Fincept kendi veri kaynağı değil, FMP'ye işaret ediyor. avo'nun homesrv'deki kopyasında ek sağlayıcı varsa
ayrı thread'in yazacağı `/mnt/project-files/fincept_providers_2026-11-22.md` ile tekrar bakılabilir.

## 7. Öneri

1. **Tazelik ve UW yerine: TickerInside.** Bedava, anahtarsız, 133/133 kapsıyor, lisansı tam bizim kullanımımıza
   izin veriyor (her gece kopya + kendi serini kurma). İş yükü: fon başına bir GET veya tek `funds.json`;
   CUSIP yok, ticker var (bizim için daha kolay). Tek şart: dashboard'da holdings gösterilen yere bir atıf linki.
2. **Tarihçe ve denetlenebilir taban: SEC N-PORT toplu zip'leri** (C7'de avo'nun onayladığı indirme). TickerInside'ın
   tarihçesini programlı biriktirmek **lisansen yasak**, o yüzden geçmiş SEC'ten gelmeli.
3. **Kendi iShares okuyucumuzu genişletmek** ucuz bir ek: ring-1'deki 45 fonun çoğu iShares ve `latest-holdings.csv`
   anahtarsız çalışıyor. TickerInside'a ikinci kaynak/doğrulama olur.
4. **Alpaca, FMP, EODHD, Polygon, Tiingo, Fincept: hayır.** Ya veri yok ya para karşılığı aynı şey.

### Yapılacak iş (TickerInside yolu için)
- `rcdata/build/spine/etf_holdings.py`'ye yeni bir sağlayıcı: `tickerinside`, fon başına `fund/<t>.json`,
  ağırlık + `holdings_as_of` + `source_layer` + `cite_as` saklanır; `provider` kolonu zaten var.
- `funds.json` tek istekle hangi fonun günlük/N-PORT olduğunu veriyor → sweep listesi oradan.
- Okuyucu sırası: ihraççı dosyamız → TickerInside günlük → TickerInside N-PORT → kendi `sec/nport` Parquet'i.
- UI: holdings kartında kaynak + tarih + TickerInside linki (lisans şartı).
- Yabancı hisseler `7203.JP` gibi anahtarlanıyor; eşleme kuralı gerekiyor. CUSIP gelmiyor.

## 8. TickerInside'ın holdings dışında verdiği, **ÖLÇÜLMEMİŞ** uçlar

Aşağıdakiler sitenin kendi anlattığı yetenekler; bu araştırmada **hiçbiri çağrılmadı, hiçbir sayı ölçülmedi.**
Kapsama, tazelik, lisans (tarihçe/flows'un CC BY dışında olduğunu hatırla, §2) ve kota tarafı açık. Bir sonraki
ölçümün listesi:

| Uç | Ne iddia ediliyor | Durum |
|---|---|---|
| ETF para akışları (flows) | fona giren/çıkan para | **ölçülmedi** — lisans: CC BY **değil** |
| Bir hisseyi hangi ETF'ler tutuyor | hisseden fona ters arama | **ölçülmedi** |
| İki ETF'in örtüşmesi (overlap) | ortak pozisyon ağırlığı | **ölçülmedi** |
| Portföy look-through | ETF listesinden altındaki gerçek hisse dağılımı ve risk | **ölçülmedi** |

Günlük okunan ihraççı kümesinde (472 fon) hangi hisselerin alınıp satıldığı da aynı kümede duruyor; o da
**ölçülmedi**. §7'nin önerisi yalnızca holdings'e dayanıyor, bu satırlara dayanmıyor.

<sub>Her sayı yukarıda adı geçen canlı çağrıdan veya repo satırından. Tahmin yok.</sub>
