"""FinancialModelEngine — ticker-bazlı finansal analiz motoru.

Asymmetric Growth Hunter taraması (``asymmetric_growth_hunter``) + Fin Research
(Quick Remarks + DCF / üç-tablo / comps / kredi / duyarlılık) + paylaşılan
ticker store.

Kaynak: yalnızca kendi store'u. Tablolar fundamentals serving katmanından, fiyat/piyasa değeri/pay/beta prices
store'dan, comps çarpanları ikisinden birlikte. Yahoo #645 ile tamamen kalktı (avo 10 Kas 2026, B seçeneği):
board hiçbir sağlayıcıya istek atmaz, SEC yıllık verisi olmayan isim model almaz.
"""

__all__ = ["run"]
