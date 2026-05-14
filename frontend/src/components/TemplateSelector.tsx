import type { TemplateChoice } from "../types";

const TEMPLATES: { value: TemplateChoice; label: string; desc: string }[] = [
  { value: "article", label: "article", desc: "Default LaTeX class" },
  { value: "ieee", label: "IEEE Transactions", desc: "IEEEtran journal style" },
  { value: "acm", label: "ACM SIGCONF", desc: "acmart conference proceedings" },
  { value: "springer", label: "Springer LNCS", desc: "llncs lecture notes class" },
];

interface Props {
  value: TemplateChoice;
  onChange: (v: TemplateChoice) => void;
  disabled?: boolean;
}

export function TemplateSelector({ value, onChange, disabled }: Props) {
  return (
    <fieldset className="template-grid" disabled={disabled} aria-label="Output LaTeX template">
      {TEMPLATES.map((t) => (
        <label key={t.value}>
          <input
            type="radio"
            name="template"
            value={t.value}
            checked={value === t.value}
            onChange={() => onChange(t.value)}
          />
          {t.label}
          <span className="desc">{t.desc}</span>
        </label>
      ))}
    </fieldset>
  );
}
