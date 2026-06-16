import { getConcept } from '../concepts'
import { useConcept } from './ConceptModal'

interface Props {
  conceptKey: string
  label?: string
}

export default function InfoButton({ conceptKey, label }: Props) {
  const { openConcept } = useConcept()

  if (!getConcept(conceptKey)) return null

  return (
    <button
      type="button"
      className="info-btn"
      aria-label={label ?? `${conceptKey} 설명 보기`}
      onClick={(e) => {
        e.stopPropagation()
        openConcept(conceptKey)
      }}
    >
      ?
    </button>
  )
}
