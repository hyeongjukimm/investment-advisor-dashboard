def test_bootstrap_reloads_cached_presentation_modules(monkeypatch):
    import data_lineage
    import dashboard_utils
    from presentation_bootstrap import refresh_presentation_modules
    monkeypatch.delitem(data_lineage.SOURCE_CATALOG, 'provisional_product')
    monkeypatch.setattr(dashboard_utils, 'sidebar_guide_sections', lambda: {'산업 스크리너':'old'})
    sources, guides=refresh_presentation_modules()
    assert 'getPrlstMmUtPrviExpAcrs' in sources.source_caption('provisional_product')
    assert '산업 스크리너' not in guides.sidebar_guide_sections()
    assert '종목 후보' not in guides.sidebar_guide_sections()
