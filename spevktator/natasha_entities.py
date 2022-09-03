from natasha import (
    Segmenter,
    MorphVocab,
    NewsEmbedding,
    NewsMorphTagger,
    NewsSyntaxParser,
    NewsNERTagger,
    NamesExtractor,
    Doc,
)

segmenter = Segmenter()
morph_vocab = MorphVocab()

emb = NewsEmbedding()
morph_tagger = NewsMorphTagger(emb)
syntax_parser = NewsSyntaxParser(emb)
ner_tagger = NewsNERTagger(emb)

names_extractor = NamesExtractor(morph_vocab)


def named_entity_normalization(text):
    doc = Doc(text)
    # print(doc)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    for token in doc.tokens:
        token.lemmatize(morph_vocab)
    doc.parse_syntax(syntax_parser)
    doc.tag_ner(ner_tagger)

    for span in doc.spans:
        span.normalize(morph_vocab)

    # print(doc.spans)
    # start=6, stop=13, type='LOC', text='Израиля', tokens=[...], normal='Израиль'
    return [
        {
            "text": _.text,
            "normal": _.normal,
            "type": _.type,
            "start": _.start,
            "stop": _.stop,
        }
        for _ in doc.spans
    ]


if __name__ == "__main__":
    text = """
    В районе Энергодара сорвана попытка высадки десанта ВСУ: https://life.ru/p/1520864
    """
    print(named_entity_normalization(text))
