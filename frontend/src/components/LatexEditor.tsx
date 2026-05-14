import { EditorView, Decoration, DecorationSet, lineNumbers } from "@codemirror/view";
import { Compartment, EditorState, StateEffect, StateField } from "@codemirror/state";
import { StreamLanguage } from "@codemirror/language";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { useEffect, useRef } from "react";

interface Props {
  value: string;
  errorLine: number | null;
}

const setErrorLine = StateEffect.define<number | null>();

const errorLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    value = value.map(tr.changes);
    for (const eff of tr.effects) {
      if (eff.is(setErrorLine)) {
        if (eff.value === null) {
          value = Decoration.none;
        } else {
          const doc = tr.state.doc;
          if (eff.value >= 1 && eff.value <= doc.lines) {
            const line = doc.line(eff.value);
            value = Decoration.set([
              Decoration.line({ attributes: { style: "background-color: rgba(239, 68, 68, 0.18);" } }).range(line.from),
            ]);
          }
        }
      }
    }
    return value;
  },
  provide: (f) => EditorView.decorations.from(f),
});

const baseTheme = EditorView.theme({
  "&": { height: "100%", fontSize: "13px", backgroundColor: "transparent" },
  ".cm-scroller": { fontFamily: "var(--mono)" },
  ".cm-content": { padding: "0.6rem 0" },
  ".cm-gutters": { backgroundColor: "transparent", color: "var(--text-dim)", border: "none" },
  ".cm-activeLine": { backgroundColor: "rgba(34, 211, 238, 0.05)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent" },
});

export function LatexEditor({ value, errorLine }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const readOnlyCompartment = useRef(new Compartment()).current;

  useEffect(() => {
    if (!hostRef.current) return;
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        StreamLanguage.define(stex),
        baseTheme,
        errorLineField,
        readOnlyCompartment.of(EditorState.readOnly.of(false)),
        EditorView.lineWrapping,
      ],
    });
    const view = new EditorView({ state, parent: hostRef.current });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    if (view.state.doc.toString() === value) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
  }, [value]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({ effects: setErrorLine.of(errorLine) });
    if (errorLine !== null && errorLine >= 1 && errorLine <= view.state.doc.lines) {
      const line = view.state.doc.line(errorLine);
      view.dispatch({
        selection: { anchor: line.from },
        effects: EditorView.scrollIntoView(line.from, { y: "center" }),
      });
    }
  }, [errorLine]);

  return <div ref={hostRef} className="editor-shell" aria-label="Generated LaTeX source" />;
}
