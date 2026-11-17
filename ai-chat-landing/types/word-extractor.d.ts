// minimal ambient types for word-extractor (no @types package exists)
declare module "word-extractor" {
  class WordDocument {
    getBody(): string
    getHeaders(): string
    getFooters(): string
    getFootnotes(): string
    getEndnotes(): string
    getTextboxes(): string
  }
  class WordExtractor {
    extract(source: string | Buffer): Promise<WordDocument>
  }
  export = WordExtractor
}