import type {
  DataValidation,
  Validation,
  ValidationGroup,
} from '../api'
import InfoButton from './InfoButton'

interface Props {
  validations: Validation[]
  dataValidation: DataValidation
}

const GROUP_LABELS: Record<ValidationGroup, string> = {
  G2: '자금·리스크',
  G3: '견고성',
  G4: '시장구조',
}

const GROUP_ORDER: ValidationGroup[] = ['G2', 'G3', 'G4']

function Badge({ passed }: { passed: boolean }) {
  return (
    <span className={`badge ${passed ? 'badge-pass' : 'badge-fail'}`}>
      {passed ? '✓' : '✗'}
    </span>
  )
}

export default function ScoreCard({ validations, dataValidation }: Props) {
  const passedCount = validations.filter((v) => v.passed).length
  const total = validations.length

  return (
    <div className="card">
      <div className="scorecard-header">
        <h2 className="card-title">검증 스코어카드</h2>
        <span className="scorecard-tally">
          통과 {passedCount} / {total}
        </span>
      </div>

      <div
        className={`data-banner ${
          dataValidation.passed ? 'data-banner-ok' : 'data-banner-bad'
        }`}
      >
        <div className="data-banner-head">
          <Badge passed={dataValidation.passed} />
          <span>
            데이터 검증 {dataValidation.passed ? '통과' : '실패'}
          </span>
          <InfoButton conceptKey="data_validation" />
        </div>
        {dataValidation.issues.length > 0 && (
          <ul className="data-banner-list issues">
            {dataValidation.issues.map((issue, i) => (
              <li key={`issue-${i}`}>이슈: {issue}</li>
            ))}
          </ul>
        )}
        {dataValidation.warnings.length > 0 && (
          <ul className="data-banner-list warnings">
            {dataValidation.warnings.map((w, i) => (
              <li key={`warn-${i}`}>경고: {w}</li>
            ))}
          </ul>
        )}
      </div>

      {GROUP_ORDER.map((group) => {
        const rows = validations.filter((v) => v.group === group)
        if (rows.length === 0) return null
        return (
          <div key={group} className="score-group">
            <h3 className="score-group-title">
              <span className="score-group-tag">{group}</span>
              {GROUP_LABELS[group]}
            </h3>
            <ul className="score-grid">
              {rows.map((v) => (
                <li
                  key={v.name}
                  className={`score-item ${
                    v.passed ? 'score-item-pass' : 'score-item-fail'
                  }`}
                >
                  <div className="score-item-head">
                    <span className="score-item-name">{v.name}</span>
                    <InfoButton conceptKey={v.name} />
                    <Badge passed={v.passed} />
                  </div>
                  <span className="score-item-message">{v.message}</span>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
