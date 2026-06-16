import { createContext, useContext, useMemo, useState } from 'react'
import { getConcept } from '../concepts'
import Modal from './Modal'

interface ConceptContextValue {
  openConcept: (key: string) => void
}

const ConceptContext = createContext<ConceptContextValue | null>(null)

export function ConceptProvider({ children }: { children: React.ReactNode }) {
  const [key, setKey] = useState<string | null>(null)

  const value = useMemo<ConceptContextValue>(
    () => ({ openConcept: (k: string) => setKey(k) }),
    [],
  )

  const concept = key !== null ? getConcept(key) : undefined

  return (
    <ConceptContext.Provider value={value}>
      {children}
      <Modal
        open={key !== null && !!concept}
        title={concept?.title ?? ''}
        onClose={() => setKey(null)}
      >
        {concept && (
          <div className="modal-body">
            <p className="modal-lead">{concept.oneLiner}</p>
            <div className="modal-section">
              <div className="modal-section-label">쉽게</div>
              <p className="modal-section-body">{concept.easy}</p>
            </div>
            {concept.detail && (
              <div className="modal-section">
                <div className="modal-section-label">자세히</div>
                <p className="modal-section-body">{concept.detail}</p>
              </div>
            )}
            {concept.howToRead && (
              <div className="modal-section">
                <div className="modal-section-label">읽는 법</div>
                <p className="modal-section-body">{concept.howToRead}</p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </ConceptContext.Provider>
  )
}

export function useConcept(): ConceptContextValue {
  const ctx = useContext(ConceptContext)
  if (!ctx) {
    throw new Error('useConcept must be used within a ConceptProvider')
  }
  return ctx
}
