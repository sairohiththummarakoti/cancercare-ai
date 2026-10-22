# Authorized guideline files

This folder intentionally contains no NCCN content. Add only documents that you are authorized to access, process through the OpenAI API, and use in this demonstration. The application does not download or scrape guidelines.

## React / FastAPI workspace authorization

The new clinical workspace additionally requires an actual `publisher` and these explicit Boolean attestations on **every** manifest entry before it permits external model processing:

```json
"authorized": true,
"allow_external_processing": true,
"version_verified": true
```

Set them only after verifying your actual source permissions, permission to send excerpts to the configured provider, and the edition printed in the document. They record your attestation; the software cannot grant a license or independently verify it. The service generates stable source identifiers from local filenames. The example starts with all flags false. A missing or false flag makes the whole collection unavailable to the FastAPI generation path. MedGUIDE MCQA remains a separate research collection and cannot authorize guideline-based treatment claims.

The legacy Streamlit app has its earlier manifest checks; the stronger explicit authorization gate is enforced by the new FastAPI workspace.

1. Copy your authorized text-based PDF, UTF-8 TXT, or Markdown files into this folder.
2. Copy `manifest.example.json` to `manifest.json`.
3. Replace the example filename, title, and version with the exact metadata from each source. Add one entry per file. Keep `section` empty if a section label is not known. The example placeholders are deliberately rejected.
4. Start the app and select live analysis. The app will show how many usable source files are available and report excluded files.

The actual manifest has this shape:

```json
{
  "files": [
    {
      "file": "your-authorized-file.pdf",
      "title": "Exact title printed in your source",
      "version": "Exact version or publication year printed in your source",
      "section": "Optional exact section label",
      "cancer_types": ["breast"]
    }
  ]
}
```

The example text above describes the fields; it is not real guideline metadata. Do not invent a version. A filename or a local file modification date does not establish a publication year. If a PDF contains multiple sections, omit `section` rather than assigning one section label to the entire document. Citations display the physical PDF page number, which can differ from a printed page label. Text sources use a supplied section label, when present, and an explicitly labeled text-chunk number.

Only files explicitly listed in `manifest.json` are indexed. Paths must remain inside this folder; symlinks, parent traversal, other file types, missing metadata, password-protected PDFs, and unreadable files are excluded. Image-only PDFs require OCR outside this MVP. Each source is limited to 25 MB, PDFs to 800 pages, the manifest to 100 entries, and the corpus to 10,000 chunks.

The index uses OpenAI embeddings and NumPy cosine similarity. It returns at most five chunks above the configured threshold. Similarity is a search heuristic, not clinical confidence or proof that a treatment applies. The assessment stage separately checks claim support and missing information. Corpus instructions are untrusted data and must never control the application.

Index files contain guideline excerpts, metadata, and embeddings. They are cached locally under the configured cache directory and must receive the same protection as the source documents. Patient text, search queries, and query embeddings are not cached. Changing source contents, metadata, embedding model, or chunking settings causes a new index to be built. Corrupt caches are rebuilt without using pickle. Remove the local cache if your source permissions change or your license requires deletion.

An empty corpus, absent manifest, missing version/title, or no matching evidence prevents a purported NCCN-grounded treatment assessment. The bundled sample walkthrough is explicitly separate from this live guideline index.
