import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  fetchPassageTranslationNames,
  importPassageTranslation,
  importPassageTranslationFromFile,
} from '../api/passages'
import { fetchSystemLanguages } from '../api/systemLanguages'

type PassageImportPanelProps = {
  onImported: (message: string) => void
}

export function PassageImportPanel({ onImported }: PassageImportPanelProps) {
  const [languages, setLanguages] = useState<string[]>([])
  const [language, setLanguage] = useState('')
  const [name, setName] = useState('')
  const [translationNames, setTranslationNames] = useState<string[]>([])
  const [chapterNumber, setChapterNumber] = useState('')
  const [translationText, setTranslationText] = useState('')
  const [translationFile, setTranslationFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchSystemLanguages()
      .then(({ languages: options }) => {
        setLanguages(options)
        setLanguage((current) => current || options[0] || '')
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Could not load languages'),
      )
  }, [])

  useEffect(() => {
    if (!language) {
      setTranslationNames([])
      return
    }
    fetchPassageTranslationNames(language)
      .then(({ names }) => setTranslationNames(names))
      .catch(() => setTranslationNames([]))
  }, [language])

  function handleFileChange(file: File | null) {
    setTranslationFile(file)
    if (file) setTranslationText('')
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!language) {
      setError('Select a translation language.')
      return
    }
    const parsedChapterNumber = Number(chapterNumber)
    if (!Number.isInteger(parsedChapterNumber) || parsedChapterNumber < 1) {
      setError('Enter a positive chapter number.')
      return
    }
    if (!translationFile && !translationText.trim()) {
      setError('Upload a text file or paste the numbered translation.')
      return
    }

    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      const result = translationFile
        ? await importPassageTranslationFromFile(translationFile, {
            language,
            chapter_number: parsedChapterNumber,
            name,
          })
        : await importPassageTranslation({
            translation_text: translationText,
            language,
            chapter_number: parsedChapterNumber,
            name,
          })
      setMessage(result.message)
      setTranslationFile(null)
      setTranslationText('')
      if (name.trim()) {
        setTranslationNames((current) =>
          current.includes(name.trim()) ? current : [...current, name.trim()].sort(),
        )
      }
      setName('')
      setChapterNumber('')
      onImported(result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Passage import failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card import-panel">
      <h3>Add passage translation</h3>
      <p className="detail-meta">
        Verse numbers may appear on separate lines or inline, such as{' '}
        <code>1 First verse 2 Second verse</code>. Unnumbered lines continue the preceding verse;
        lines beginning with <code>&lt;header&gt;</code> are ignored.
      </p>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}
      <form className="mutation-form" onSubmit={handleSubmit}>
        <fieldset>
          <legend>Translation details</legend>
          <label htmlFor="passage-language">Language</label>
          <select
            id="passage-language"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
            required
          >
            <option value="" disabled>Select a language</option>
            {languages.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <label htmlFor="passage-chapter-number">Chapter number</label>
          <input
            id="passage-chapter-number"
            type="number"
            min={1}
            step={1}
            value={chapterNumber}
            onChange={(event) => setChapterNumber(event.target.value)}
            placeholder="For example, 1"
            required
          />
          <label htmlFor="translation-name">Translation method/name (optional)</label>
          <input
            id="translation-name"
            type="text"
            list="translation-name-options"
            maxLength={255}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="For example, ULT"
          />
          <datalist id="translation-name-options">
            {translationNames.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </fieldset>

        <fieldset>
          <legend>Upload UTF-8 text file</legend>
          <input
            id="translation-file"
            type="file"
            accept=".txt,text/plain"
            onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
          />
          {translationFile ? <p className="detail-meta">Selected: {translationFile.name}</p> : null}
        </fieldset>

        <fieldset>
          <legend>Paste numbered translation</legend>
          <textarea
            id="translation-text"
            className="json-textarea"
            value={translationText}
            onChange={(event) => {
              setTranslationText(event.target.value)
              if (event.target.value.trim()) setTranslationFile(null)
            }}
            placeholder={'1 First verse text\n2 Second verse text'}
            spellCheck={false}
            disabled={Boolean(translationFile)}
          />
        </fieldset>

        <button type="submit" className="btn-primary import-questions-button" disabled={submitting}>
          {submitting ? 'Importing…' : 'Import passage'}
        </button>
      </form>
    </section>
  )
}
