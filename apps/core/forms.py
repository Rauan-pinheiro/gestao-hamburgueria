def ativar_busca(form, *nomes_campos):
    """
    Marca campos de seleção (ModelChoiceField/ChoiceField) para receber busca dinâmica
    no front-end (Tom Select — ver static/js/select-busca.js). Usar nos campos ligados a
    cadastros com muitos registros (ingredientes, itens do cardápio, fornecedores,
    categorias...), onde rolar um <select> nativo manualmente é ruim de usar.

    Uso: no __init__ do ModelForm, depois do super().__init__():
        ativar_busca(self, 'ingrediente', 'categoria')
    """
    for nome in nomes_campos:
        widget = form.fields[nome].widget
        classes = f"{widget.attrs.get('class', '')} js-select-search".strip()
        widget.attrs['class'] = classes
