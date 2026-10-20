import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
  Cell,
  LabelList,
} from "recharts";

import type { Categoria, MinedData } from "./types/mined";
import { CATEGORIAS } from "./types/mined";
import { loadMinedData } from "./data/minedDataLoader";
import { computeAlunosView, SERIE_KEY, type SemestreValor, type SeriePonto } from "./analytics/alunosView";
import { computeDisciplinasView, disciplinasDoCurso, type RankingItem } from "./analytics/disciplinasView";
import { perguntar, type ChatResposta, type Grafico, type HistoricoItem } from "./services/chatApi";

// ── Palette ────────────────────────────────────────────────────────────────
const BLUE = "#1a6fca";
const BLUE_LIGHT = "#e8f1fb";
const RED = "#e03131";
const RED_LIGHT = "#fff0f0";
const GREEN = "#10b981";
const GREEN_LIGHT = "#f0fdf8";
const YELLOW = "#d97706";
const YELLOW_LIGHT = "#fffbeb";
const PURPLE = "#7c3aed";
const TEAL = "#0891b2";
const ORANGE = "#ea580c";
const GRAY_50 = "#f8f9fb";
const GRAY_100 = "#f1f3f7";
const GRAY_200 = "#e2e6ee";
const GRAY_400 = "#9aa3b8";
const GRAY_600 = "#5a6480";
const GRAY_800 = "#1e2440";
const WHITE = "#ffffff";
const SHADOW = "0 1px 4px rgba(30,36,64,0.08), 0 4px 16px rgba(30,36,64,0.06)";
const BLACK = "#000000";

const POLOS = ["Escola Politécnica"];
const TODOS_CURSOS = "Todos os Cursos";
const TODOS_PERIODOS = "Todos os Períodos";
const TODAS_DISCIPLINAS = "Todas as Disciplinas";
const TODOS_INDICADORES = "Todos os Indicadores";

// Metadados de exibição de cada categoria (rótulos e cores — nenhuma regra de negócio)
const CAT_META: Record<
  Categoria,
  { indicador: string; total: string; taxa: string; serie: string; color: string; bg: string; border: string }
> = {
  ATIVO: {
    indicador: "Alunos Ativos",
    total: "Total de Alunos Ativos",
    taxa: "Taxa de Alunos Ativos",
    serie: "Alunos Ativos",
    color: BLUE,
    bg: BLUE_LIGHT,
    border: "#bfdbfe",
  },
  EVADIDO: {
    indicador: "Evasão",
    total: "Total de Evasão",
    taxa: "Taxa de Evasão",
    serie: "Evadidos",
    color: RED,
    bg: RED_LIGHT,
    border: "#fecaca",
  },
  RETIDO: {
    indicador: "Retenção",
    total: "Total de Retenção",
    taxa: "Taxa de Retenção",
    serie: "Retidos",
    color: YELLOW,
    bg: YELLOW_LIGHT,
    border: "#fde68a",
  },
  FORMADO: {
    indicador: "Formados",
    total: "Total de Formados",
    taxa: "Taxa de Formados",
    serie: "Formados",
    color: GREEN,
    bg: GREEN_LIGHT,
    border: "#a7f3d0",
  },
};
// Opções do filtro Indicador (multiseleção; nenhuma marcada = Todos os Indicadores)
const INDICADOR_LABELS: string[] = CATEGORIAS.map((c) => CAT_META[c].indicador);
const categoriaDoLabel = (label: string) => CATEGORIAS.find((c) => CAT_META[c].indicador === label);

// ── Formatação ────────────────────────────────────────────────────────────
const fmtInt = (n: number) => Math.round(n).toLocaleString("pt-BR");
const fmtPct = (n: number) => `${n.toFixed(1)}%`;
const fmtDec1 = (n: number) => n.toFixed(1);

// ── UI base ───────────────────────────────────────────────────────────────
function Card({ children, style = {} }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{ background: WHITE, borderRadius: 12, boxShadow: SHADOW, padding: "20px 24px", minWidth: 0, ...style }}>
      {children}
    </div>
  );
}

function CardTitle({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: GRAY_800, marginBottom: 16, letterSpacing: "-0.01em" }}>
      {children}
    </div>
  );
}

const FILTER_LABEL_STYLE: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: GRAY_600,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const CHEVRON_BG = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%239aa3b8' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E")`;

const FILTER_CONTROL_STYLE: CSSProperties = {
  width: "100%",
  height: 38,
  padding: "0 32px 0 12px",
  borderWidth: "1.5px",
  borderStyle: "solid",
  borderColor: GRAY_200,
  borderRadius: 8,
  background: WHITE,
  color: GRAY_800,
  fontSize: 13,
  cursor: "pointer",
  appearance: "none",
  backgroundImage: CHEVRON_BG,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  outline: "none",
  fontFamily: "inherit",
  textAlign: "left",
};

function Dropdown({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="filter-item" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label style={FILTER_LABEL_STYLE}>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={FILTER_CONTROL_STYLE}>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Seleção múltipla com checkbox por opção.
 * value = [] significa "todos" (placeholderTodos).
 * O valor devolvido segue sempre a ordem de `options` (cronológica, no caso dos períodos).
 * `pesquisavel` adiciona um campo de busca no topo da lista (útil para listas longas).
 */
function MultiSelectDropdown({
  label,
  options,
  value,
  onChange,
  placeholderTodos,
  maxIndividuais = 2,
  rotuloPlural = "períodos",
  pesquisavel = false,
  alinharMenu = "left",
  larguraMenu = 220,
}: {
  label: string;
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  placeholderTodos: string;
  maxIndividuais?: number;
  rotuloPlural?: string;
  pesquisavel?: boolean;
  alinharMenu?: "left" | "right";
  larguraMenu?: number;
}) {
  const [open, setOpen] = useState(false);
  const [busca, setBusca] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = useMemo(() => new Set(value), [value]);

  useEffect(() => {
    if (!open) {
      setBusca("");
      return;
    }
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle(opt: string) {
    const next = new Set(selected);
    if (next.has(opt)) next.delete(opt);
    else next.add(opt);
    onChange(options.filter((o) => next.has(o)));
  }

  const resumo =
    value.length === 0
      ? placeholderTodos
      : value.length <= maxIndividuais
        ? value.join(", ")
        : `${value.length} ${rotuloPlural} selecionados`;

  const termo = busca.trim().toLocaleLowerCase("pt-BR");
  const visiveis = termo ? options.filter((o) => o.toLocaleLowerCase("pt-BR").includes(termo)) : options;

  return (
    <div ref={rootRef} className="multiselect filter-item" style={{ display: "flex", flexDirection: "column", gap: 4, position: "relative" }}>
      <label style={FILTER_LABEL_STYLE}>{label}</label>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={value.length > 0 ? value.join(", ") : placeholderTodos}
        style={{
          ...FILTER_CONTROL_STYLE,
          borderColor: open ? BLUE : GRAY_200,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {resumo}
      </button>
      {open && (
        <div
          className="multiselect-menu"
          role="listbox"
          aria-multiselectable="true"
          style={{
            position: "absolute",
            top: "100%",
            ...(alinharMenu === "right" ? { right: 0 } : { left: 0 }),
            width: larguraMenu,
            minWidth: "100%",
            marginTop: 4,
            background: WHITE,
            borderWidth: "1px",
            borderStyle: "solid",
            borderColor: GRAY_200,
            borderRadius: 8,
            boxShadow: SHADOW,
            zIndex: 50,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <button
            type="button"
            onClick={() => onChange([])}
            style={{
              background: value.length === 0 ? BLUE_LIGHT : "transparent",
              color: value.length === 0 ? BLUE : GRAY_600,
              border: "none",
              borderBottom: `1px solid ${GRAY_100}`,
              padding: "9px 12px",
              fontSize: 12.5,
              fontWeight: 600,
              textAlign: "left",
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {placeholderTodos}
          </button>
          {pesquisavel && (
            <div style={{ padding: "8px 10px", borderBottom: `1px solid ${GRAY_100}` }}>
              <input
                autoFocus
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar..."
                style={{
                  width: "100%",
                  height: 30,
                  padding: "0 10px",
                  borderWidth: "1px",
                  borderStyle: "solid",
                  borderColor: GRAY_200,
                  borderRadius: 6,
                  fontSize: 12.5,
                  color: GRAY_800,
                  background: GRAY_50,
                  outline: "none",
                  fontFamily: "inherit",
                }}
              />
            </div>
          )}
          <div className="multiselect-list" style={{ overflowY: "auto", padding: "4px 0" }}>
            {visiveis.length === 0 && (
              <div style={{ padding: "8px 12px", fontSize: 12, color: GRAY_400 }}>Nenhuma opção encontrada.</div>
            )}
            {visiveis.map((o) => {
              const checked = selected.has(o);
              return (
                <label
                  key={o}
                  role="option"
                  aria-selected={checked}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                    padding: "6px 12px",
                    lineHeight: 1.35,
                    fontSize: 12.5,
                    color: GRAY_800,
                    cursor: "pointer",
                    background: checked ? GRAY_50 : "transparent",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(o)}
                    style={{ accentColor: BLUE, cursor: "pointer", margin: "2px 0 0", flexShrink: 0 }}
                  />
                  {o}
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const TT = {
  contentStyle: {
    background: WHITE,
    borderWidth: "1px",
    borderStyle: "solid",
    borderColor: GRAY_200,
    borderRadius: 8,
    boxShadow: SHADOW,
    color: GRAY_800,
    fontSize: 12,
    padding: "8px 12px",
  },
  cursor: { fill: BLUE_LIGHT },
};

const fmtTooltip = (rotulo: string) => (v: unknown) => [Number(v).toLocaleString("pt-BR"), rotulo] as [string, string];

/** Rótulo de valor ao lado de cada barra horizontal (recebe as props do Recharts via `label`). */
function HBarLabel({
  x,
  y,
  width,
  height,
  value,
}: {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
  value?: number | string;
}) {
  return (
    <text
      x={Number(x ?? 0) + Number(width ?? 0) + 6}
      y={Number(y ?? 0) + Number(height ?? 0) / 2}
      dominantBaseline="central"
      fontSize={11}
      fill={GRAY_600}
      fontFamily="system-ui"
    >
      {Number(value ?? 0).toLocaleString("pt-BR")}
    </text>
  );
}

/** Logo inline (SVG) — troque pelo brasão real da instituição se quiser. */
function InstitutionLogo() {
  return (
    <img
      src="/logo-upe.png"
      alt="UPE"
      style={{ height: 40, width: "auto", flexShrink: 0, display: "block" }}
    />
  );
}

function MiniBar({ value, color }: { value: number; color: string }) {
  const pctv = Math.min(Math.max(value, 0), 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 90 }}>
      <div style={{ flex: 1, height: 6, background: GRAY_100, borderRadius: 3 }}>
        <div style={{ width: `${pctv}%`, height: "100%", background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 11, color: GRAY_600, minWidth: 38, textAlign: "right" }}>
        {fmtPct(value)}
      </span>
    </div>
  );
}

function EmptyChart({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 12, color: GRAY_400, padding: "40px 0", textAlign: "center" }}>{children}</div>;
}

// ── Rankings de disciplinas (recebe os 10 itens já prontos de disciplinasView.ts) ──
function RankingCard({
  title,
  data,
  color,
  fmt,
}: {
  title: string;
  data: RankingItem[];
  color: string;
  fmt: (v: number) => string;
}) {
  const max = data.length > 0 ? Math.max(...data.map((d) => d.valor), 1) : 1;
  return (
    <Card>
      <div style={{ fontSize: 13, fontWeight: 700, color: GRAY_800, marginBottom: 16 }}>{title}</div>
      {data.length === 0 ? (
        <div style={{ fontSize: 12, color: GRAY_400 }}>Sem dados para os filtros atuais.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {data.map((d) => (
            <div key={d.disciplina} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                title={d.disciplina}
                style={{
                  fontSize: 11,
                  color: GRAY_600,
                  minWidth: 150,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {d.disciplina}
              </span>
              <div style={{ flex: 1, height: 8, background: GRAY_100, borderRadius: 4 }}>
                <div
                  style={{ width: `${(d.valor / max) * 100}%`, height: "100%", background: color, borderRadius: 4 }}
                />
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: GRAY_800,
                  minWidth: 44,
                  textAlign: "right",
                  fontFamily: "monospace",
                }}
              >
                {fmt(d.valor)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Série histórica de alunos (só as categorias visíveis) ──────────────────
function SerieHistoricaAlunosChart({ data, categorias }: { data: SeriePonto[]; categorias: Categoria[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 4, right: 24, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} vertical={false} />
        <XAxis dataKey="periodo" tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
        <Tooltip {...TT} />
        <Legend wrapperStyle={{ fontSize: 11, color: GRAY_600, paddingTop: 8 }} />
        {categorias.map((c) => (
          <Line
            key={c}
            type="monotone"
            dataKey={SERIE_KEY[c]}
            name={CAT_META[c].serie}
            stroke={CAT_META[c].color}
            strokeWidth={2}
            dot={data.length <= 2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// intensidade de cor proporcional ao valor
function intensityColor(value: number, max: number, strong: string, mid: string, light: string) {
  if (max <= 0) return light;
  const ratio = value / max;
  if (ratio >= 0.66) return strong;
  if (ratio >= 0.33) return mid;
  return light;
}

/**
 * Histograma por semestre cursado. Como há muitos semestres reais (até ~27),
 * cada barra tem largura mínima e o gráfico rola na horizontal quando não cabe.
 */
const SEMESTRE_SLOT_PX = 30;
function SemestrePorPeriodoChart({
  data,
  nome,
  cores,
  vazio,
}: {
  data: SemestreValor[];
  nome: string;
  cores: [string, string, string];
  vazio: string;
}) {
  if (data.length === 0) return <EmptyChart>{vazio}</EmptyChart>;
  const max = Math.max(...data.map((d) => d.valor), 1);
  return (
    <div className="h-scroll" style={{ overflowX: "auto", overflowY: "hidden" }}>
      <div style={{ minWidth: data.length * SEMESTRE_SLOT_PX + 40, height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }} barCategoryGap="20%">
            <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} vertical={false} />
            <XAxis
              dataKey="semestre"
              tick={{ fontSize: 10, fill: GRAY_400 }}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
            <YAxis tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip {...TT} formatter={fmtTooltip("Alunos")} labelFormatter={(l) => `${l}º semestre`} />
            <Bar dataKey="valor" name={nome} radius={[4, 4, 0, 0]} maxBarSize={28}>
              {data.map((entry) => (
                <Cell key={entry.semestre} fill={intensityColor(entry.valor, max, cores[0], cores[1], cores[2])} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function useUpdatingFlag() {
  const [updating, setUpdating] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  function applyFilter(fn: () => void) {
    fn();
    setUpdating(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setUpdating(false), 300);
  }
  return { updating, applyFilter };
}

function PanelHeader({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        marginBottom: 24,
        flexWrap: "wrap",
        gap: 16,
      }}
    >
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: GRAY_800, lineHeight: 1.2 }}>{title}</div>
        <div style={{ fontSize: 13, color: GRAY_400, marginTop: 4 }}>{subtitle}</div>
      </div>
      <div className="filters-row">{children}</div>
    </div>
  );
}

// ── Painel: Análise de Alunos ────────────────────────────────────────────────
function AlunasPanel({ data }: { data: MinedData }) {
  const [curso, setCurso] = useState(TODOS_CURSOS);
  const [periodos, setPeriodos] = useState<string[]>([]);
  const [indicadoresSelecionados, setIndicadoresSelecionados] = useState<Categoria[]>([]);
  const [polo] = useState(POLOS[0]);
  const { updating, applyFilter } = useUpdatingFlag();

  const view = useMemo(
    () =>
      computeAlunosView(data, {
        curso: curso === TODOS_CURSOS ? null : curso,
        periodosSelecionados: periodos,
        indicadoresSelecionados,
      }),
    [data, curso, periodos, indicadoresSelecionados]
  );

  const cursoOptions = [TODOS_CURSOS, ...data.alunosFiltros.cursos];

  // KPI cards: linha de totais + linha de taxas, só para as categorias devolvidas pela view
  const kpiCards = [
    ...view.kpis.map((k) => ({ key: `${k.categoria}-total`, label: CAT_META[k.categoria].total, value: fmtInt(k.total), cat: k.categoria })),
    ...view.kpis.map((k) => ({ key: `${k.categoria}-taxa`, label: CAT_META[k.categoria].taxa, value: fmtPct(k.taxa), cat: k.categoria })),
  ];

  const mostraEvasao = view.categoriasVisiveis.includes("EVADIDO");
  const mostraFormacao = view.categoriasVisiveis.includes("FORMADO");
  const nGraficos = (mostraEvasao ? 2 : 0) + (mostraFormacao ? 1 : 0);

  return (
    <div
      style={{
        padding: "24px 28px",
        maxWidth: 1400,
        margin: "0 auto",
        opacity: updating ? 0.6 : 1,
        transition: "opacity 0.3s",
      }}
    >
      <PanelHeader title="Painel de Análise de Alunos" subtitle="Visão geral do desempenho acadêmico dos estudantes">
        <Dropdown label="Polo" options={POLOS} value={polo} onChange={() => {}} />
        <MultiSelectDropdown
          label="Período Letivo"
          options={data.alunosFiltros.periodos}
          value={periodos}
          placeholderTodos={TODOS_PERIODOS}
          onChange={(v) => applyFilter(() => setPeriodos(v))}
        />
        <Dropdown label="Curso" options={cursoOptions} value={curso} onChange={(v) => applyFilter(() => setCurso(v))} />
        <MultiSelectDropdown
          label="Indicador"
          options={INDICADOR_LABELS}
          value={indicadoresSelecionados.map((c) => CAT_META[c].indicador)}
          placeholderTodos={TODOS_INDICADORES}
          rotuloPlural="indicadores"
          alinharMenu="right"
          onChange={(labels) =>
            applyFilter(() =>
              setIndicadoresSelecionados(
                labels.map(categoriaDoLabel).filter((c): c is Categoria => c !== undefined)
              )
            )
          }
        />
      </PanelHeader>

      {/* KPI cards: um par (total + taxa) por indicador visível */}
      <div
        className="kpi-grid"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${view.kpis.length}, minmax(0, 220px))`,
          gap: 14,
          marginBottom: 24,
        }}
      >
        {kpiCards.map((k) => (
          <div
            key={k.key}
            style={{
              background: CAT_META[k.cat].bg,
              borderWidth: "1px",
              borderStyle: "solid",
              borderColor: CAT_META[k.cat].border,
              borderRadius: 12,
              padding: "12px 18px",
            }}
          >
            <div style={{ fontSize: 15, color: GRAY_600, fontWeight: 600, marginBottom: 8, lineHeight: 1.3 }}>
              {k.label}
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: GRAY_800, lineHeight: 1 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {view.totalAlunos === 0 && (
        <Card style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: GRAY_600 }}>Nenhum estudante encontrado para os filtros selecionados.</div>
        </Card>
      )}

      <Card style={{ marginBottom: 20 }}>
        <CardTitle>Séries Históricas</CardTitle>
        <SerieHistoricaAlunosChart data={view.serieHistorica} categorias={view.categoriasVisiveis} />
      </Card>

      {nGraficos > 0 && (
        <div
          className="charts-grid"
          style={{ ["--cols" as string]: String(nGraficos), gap: 16, marginBottom: 20 } as CSSProperties}
        >
          {mostraEvasao && (
            <Card>
              <CardTitle>Evasão por Semestre Cursado</CardTitle>
              <SemestrePorPeriodoChart
                data={view.evasaoPorSemestre}
                nome="Evadidos"
                cores={[RED, "#f87171", "#fca5a5"]}
                vazio="Sem evasões registradas para os filtros atuais."
              />
            </Card>
          )}

          {mostraFormacao && (
            <Card>
              <CardTitle>Formação por Semestre Cursado</CardTitle>
              <SemestrePorPeriodoChart
                data={view.formacaoPorSemestre}
                nome="Formados"
                cores={["#059669", GREEN, "#6ee7b7"]}
                vazio="Sem formaturas registradas para os filtros atuais."
              />
            </Card>
          )}

          {mostraEvasao && (
            <Card>
              <CardTitle>Evasão pelo Tipo de Saída</CardTitle>
              {view.evasaoPorTipoSaida.length === 0 ? (
                <EmptyChart>Sem evasões registradas para os filtros atuais.</EmptyChart>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart layout="vertical" data={view.evasaoPorTipoSaida} margin={{ top: 0, right: 56, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
                    <YAxis
                      type="category"
                      dataKey="tipo"
                      tick={{ fontSize: 10.5, fill: GRAY_600 }}
                      axisLine={false}
                      tickLine={false}
                      width={148}
                    />
                    <Tooltip {...TT} formatter={fmtTooltip("Evadidos")} />
                    <Bar dataKey="valor" fill={RED} radius={[0, 4, 4, 0]} maxBarSize={24} label={<HBarLabel />} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>
          )}
        </div>
      )}

      <div style={{ marginTop: 4, textAlign: "center", color: GRAY_400, fontSize: 11, paddingBottom: 24 }}>
        Dados reais — {fmtInt(view.totalAlunos)} estudante(s) no recorte atual
        {periodos.length === 0 ? " (situação mais recente do histórico completo)" : ""} · Sigadash.v2 — UPE
      </div>
    </div>
  );
}

// ── Painel: Análise de Disciplinas ──────────────────────────────────────────
function DisciplinasPanel({ data }: { data: MinedData }) {
  const [curso, setCurso] = useState(TODOS_CURSOS);
  const [periodos, setPeriodos] = useState<string[]>([]);
  const [disciplinasSelecionadas, setDisciplinasSelecionadas] = useState<string[]>([]);
  const [polo] = useState(POLOS[0]);
  const { updating, applyFilter } = useUpdatingFlag();

  const cursoFiltro = curso === TODOS_CURSOS ? null : curso;
  const disciplinasDisponiveis = useMemo(() => disciplinasDoCurso(data, cursoFiltro), [data, cursoFiltro]);

  // ao trocar de curso, remove da seleção as disciplinas que não existem nele
  useEffect(() => {
    const disponiveis = new Set(disciplinasDisponiveis);
    if (disciplinasSelecionadas.some((d) => !disponiveis.has(d))) {
      setDisciplinasSelecionadas(disciplinasSelecionadas.filter((d) => disponiveis.has(d)));
    }
  }, [disciplinasSelecionadas, disciplinasDisponiveis]);

  const view = useMemo(
    () =>
      computeDisciplinasView(data, {
        curso: cursoFiltro,
        periodosSelecionados: periodos,
        disciplinasSelecionadas,
      }),
    [data, cursoFiltro, periodos, disciplinasSelecionadas]
  );

  const cursoOptions = [TODOS_CURSOS, ...data.disciplinasRows.cursos];
  const { kpis } = view;

  const kpiCards = [
    { label: "Taxa de Aprovação", value: fmtPct(kpis.taxaAprovacao), color: BLACK, bg: BLUE_LIGHT, border: "#bfdbfe" },
    { label: "Taxa de Reprovação", value: fmtPct(kpis.taxaReprovacao), color: BLACK, bg: RED_LIGHT, border: "#fecaca" },
    { label: "Total de Aprovados", value: fmtInt(kpis.totalAprovados), color: BLACK, bg: BLUE_LIGHT, border: "#bfdbfe" },
    { label: "Total de Reprovados", value: fmtInt(kpis.totalReprovados), color: BLACK, bg: RED_LIGHT, border: "#fecaca" },
  ];

  return (
    <div
      style={{
        padding: "24px 28px",
        maxWidth: 1400,
        margin: "0 auto",
        opacity: updating ? 0.6 : 1,
        transition: "opacity 0.3s",
      }}
    >
      <PanelHeader title="Painel de Análise de Disciplinas" subtitle="Visão geral do desempenho das disciplinas acadêmicas">
        <Dropdown label="Polo" options={POLOS} value={polo} onChange={() => {}} />
        <Dropdown label="Curso" options={cursoOptions} value={curso} onChange={(v) => applyFilter(() => setCurso(v))} />
        <MultiSelectDropdown
          label="Período Letivo"
          options={data.disciplinasRows.periodos}
          value={periodos}
          placeholderTodos={TODOS_PERIODOS}
          onChange={(v) => applyFilter(() => setPeriodos(v))}
        />
        <MultiSelectDropdown
          label="Disciplina"
          options={disciplinasDisponiveis}
          value={disciplinasSelecionadas}
          placeholderTodos={TODAS_DISCIPLINAS}
          rotuloPlural="disciplinas"
          maxIndividuais={1}
          pesquisavel
          alinharMenu="right"
          larguraMenu={360}
          onChange={(v) => applyFilter(() => setDisciplinasSelecionadas(v))}
        />
      </PanelHeader>

      <div className="kpi-grid" style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 220px))", gap: 14, marginBottom: 24 }}>
        {kpiCards.map((k) => (
          <div
            key={k.label}
            style={{
              background: k.bg,
              borderWidth: "1px",
              borderStyle: "solid",
              borderColor: k.border,
              borderRadius: 12,
              padding: "12px 18px",
            }}
          >
            <div style={{ fontSize: 15, color: GRAY_600, fontWeight: 600, marginBottom: 8, lineHeight: 1.3 }}>{k.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: k.color, lineHeight: 1 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Rankings — grade fixa 2 linhas × 3 colunas */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: GRAY_800, marginBottom: 14 }}>Rankings de Disciplinas</div>
        <div className="rankings-grid" style={{ marginBottom: 20 }}>
          <RankingCard title="Top 10 Disciplinas com Mais Aprovados" data={view.rankingMaisAprovados} color={BLUE} fmt={fmtInt} />
          <RankingCard title="Top 10 Disciplinas com Mais Reprovados" data={view.rankingMaisReprovados} color={RED} fmt={fmtInt} />
          <RankingCard title="Top 10 Disciplinas com Melhor Média Final" data={view.rankingMelhorMedia} color={TEAL} fmt={fmtDec1} />
          <RankingCard title="Top 10 Disciplinas com Menos Faltas" data={view.rankingMelhorFrequencia} color={PURPLE} fmt={fmtDec1} />
          <RankingCard title="Top 10 Disciplinas com Mais Faltas" data={view.rankingMaisFaltas} color={ORANGE} fmt={fmtDec1} />
          <RankingCard title="Top 10 Disciplinas com Pior Média Final" data={view.rankingPiorMedia} color={YELLOW} fmt={fmtDec1} />
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: GRAY_800, marginBottom: 14 }}>Série Histórica</div>
        <div className="charts-grid" style={{ ["--cols" as string]: "2", gap: 16 } as CSSProperties}>
          <Card>
            <CardTitle>Aprovados por Período</CardTitle>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={view.serieHistorica} margin={{ top: 4, right: 16, left: 0, bottom: 0 }} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} vertical={false} />
                <XAxis dataKey="periodo" tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
                <Tooltip {...TT} formatter={fmtTooltip("Aprovados")} />
                <Bar dataKey="aprovados" name="Aprovados" fill={BLUE} radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card>
            <CardTitle>Reprovados por Período</CardTitle>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={view.serieHistorica} margin={{ top: 4, right: 16, left: 0, bottom: 0 }} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} vertical={false} />
                <XAxis dataKey="periodo" tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: GRAY_400 }} axisLine={false} tickLine={false} />
                <Tooltip {...TT} formatter={fmtTooltip("Reprovados")} />
                <Bar dataKey="reprovados" name="Reprovados" fill={RED} radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      </div>

      {/* Tabela curso x disciplina */}
      <Card style={{ marginBottom: 20, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "20px 24px 12px" }}>
          <CardTitle>Tabela de Disciplinas por Curso ({view.tabela.length.toLocaleString("pt-BR")} elementos)</CardTitle>
        </div>
        <div style={{ maxHeight: 420, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ position: "sticky", top: 0, background: GRAY_50, zIndex: 1 }}>
                {["Curso", "Disciplina", "Matrículas", "Aprovados", "Reprovados", "Taxa Aprov.", "Média Final", "Média Faltas"].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "10px 16px",
                        fontSize: 10.5,
                        fontWeight: 700,
                        color: GRAY_600,
                        letterSpacing: "0.03em",
                        textTransform: "uppercase",
                        borderBottom: `1px solid ${GRAY_200}`,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {view.tabela.map((row) => (
                <tr key={`${row.curso}::${row.disciplina}`} style={{ borderBottom: `1px solid ${GRAY_100}` }}>
                  <td style={{ padding: "8px 16px", color: GRAY_600, whiteSpace: "nowrap" }}>{row.curso}</td>
                  <td style={{ padding: "8px 16px", color: GRAY_800, fontWeight: 500 }}>{row.disciplina}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", color: GRAY_600 }}>{fmtInt(row.matriculas)}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", color: BLUE }}>{fmtInt(row.aprovados)}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", color: RED }}>{fmtInt(row.reprovados)}</td>
                  <td style={{ padding: "8px 16px" }}>
                    <MiniBar value={row.taxaAprovacao} color={row.taxaAprovacao >= 60 ? GREEN : RED} />
                  </td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", color: GRAY_600 }}>
                    {row.mediaFinal === null ? "—" : fmtDec1(row.mediaFinal)}
                  </td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", color: GRAY_600 }}>
                    {row.mediaFaltas === null ? "—" : fmtDec1(row.mediaFaltas)}
                  </td>
                </tr>
              ))}
              {view.tabela.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ padding: 24, textAlign: "center", color: GRAY_400 }}>
                    Sem dados para os filtros atuais.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ textAlign: "center", color: GRAY_400, fontSize: 11, paddingBottom: 24 }}>
        Dados reais — {fmtInt(kpis.totalMatriculas)} matrícula(s) no recorte atual · Sigadash.v2 — UPE
      </div>
    </div>
  );
}

// ── Sidebar nav items ────────────────────────────────────────────────────────
const NAV_ITEMS = [
  {
    id: "alunos",
    label: "Análise de Alunos",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M2.5 13c0-2.485 2.462-4.5 5.5-4.5s5.5 2.015 5.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "disciplinas",
    label: "Análise de Disciplinas",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="9" width="2.5" height="5" rx="1" fill="currentColor" />
        <rect x="6.5" y="6" width="2.5" height="8" rx="1" fill="currentColor" />
        <rect x="11" y="2" width="2.5" height="12" rx="1" fill="currentColor" />
      </svg>
    ),
  },
];

// ── Chat Panel (conectado ao backend: pergunta → SQL → resposta) ─────────────
type Message = {
  role: "user" | "assistant";
  text: string;
  erro?: boolean;
  resultado?: ChatResposta;
};

const SUGESTOES = [
  "Quais cursos possuem maior taxa de evasão?",
  "Quais disciplinas possuem maior taxa de reprovação?",
  "Mostre a evolução dos concluintes.",
  "Quantos alunos estão retidos hoje em cada curso?",
];

const PREVIEW_LINHAS = 5;

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  return String(v);
}

// Gráfico do chat: o backend diz o tipo e as colunas; os valores vêm de `dados` (resultado do SQL).
const SERIES_CORES = [BLUE, ORANGE, PURPLE]; // ordem fixa, validada para daltonismo
const MAX_BARRAS = 15;

function nomeColuna(c: string): string {
  const t = c.replace(/_pct$/, " (%)").replace(/_/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function abreviar(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

const fmtEixo = (v: number) => v.toLocaleString("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

function GraficoCanvas({
  grafico,
  colunas,
  dados,
  ampliado,
}: {
  grafico: Grafico;
  colunas: string[];
  dados: unknown[][];
  ampliado: boolean;
}) {
  const ix = colunas.indexOf(grafico.x);
  const iys = grafico.y.map((y) => colunas.indexOf(y));
  // Rankings/categorias longas ficam ilegíveis no painel: corta em 15. Séries por período ficam inteiras.
  const porPeriodo = dados.every((l) => /^\d{4}\.\d$/.test(String(l[ix])));
  const linhas = grafico.tipo === "linha" || porPeriodo ? dados : dados.slice(0, MAX_BARRAS);
  const rows = linhas.map((linha) => {
    const row: Record<string, string | number | null> = { [grafico.x]: String(linha[ix] ?? "—") };
    grafico.y.forEach((y, k) => {
      const v = linha[iys[k]];
      row[y] = typeof v === "number" ? v : null;
    });
    return row;
  });

  const tick = { fontSize: ampliado ? 11 : 9, fill: GRAY_400 };
  const rotulo = (max: number) => (v: string) => (ampliado ? v : abreviar(v, max));
  const maiorRotulo = Math.max(0, ...rows.map((r) => String(r[grafico.x]).length));
  // Mesmo que chegue "barra" com nomes longos, desenha na horizontal: no eixo X eles se sobrepõem.
  const tipo = grafico.tipo === "barra" && !porPeriodo && maiorRotulo > 14 ? "barra_horizontal" : grafico.tipo;
  // Ampliado: com muitos itens ou rótulos médios, inclina os rótulos do eixo X em vez de sobrepor.
  const inclinar = ampliado && rows.length * Math.max(maiorRotulo, 4) * 7 > 760;
  const tooltip = (
    <Tooltip
      {...TT}
      formatter={(v: unknown, nome: unknown) =>
        [typeof v === "number" ? v.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) : "—", String(nome)] as [string, string]
      }
    />
  );
  const legenda = grafico.y.length > 1 && <Legend wrapperStyle={{ fontSize: ampliado ? 11 : 10, color: GRAY_600 }} />;
  const nota =
    dados.length > rows.length ? (
      <div style={{ fontSize: 10, color: GRAY_400, marginTop: 2 }}>
        Mostrando {rows.length} de {dados.length} itens
      </div>
    ) : null;

  if (tipo === "barra_horizontal") {
    // No painel estreito o nome vai acima de cada barra (usa toda a largura); ampliado, num eixo Y largo.
    const altura = Math.max(ampliado ? 240 : 140, rows.length * 30 + 40);
    const rotuloAcima = (props: { x?: number | string; y?: number | string; value?: unknown }) => (
      <text x={Number(props.x)} y={Number(props.y) - 4} fontSize={9.5} fill={GRAY_600}>
        {abreviar(String(props.value ?? ""), 40)}
      </text>
    );
    return (
      <>
        <ResponsiveContainer width="100%" height={altura}>
          <BarChart
            layout="vertical"
            data={rows}
            margin={{ top: ampliado ? 0 : 12, right: 12, left: 0, bottom: 0 }}
            barCategoryGap={ampliado ? "20%" : "45%"}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} horizontal={false} />
            <XAxis type="number" tick={tick} axisLine={false} tickLine={false} tickFormatter={fmtEixo} />
            <YAxis
              type="category"
              dataKey={grafico.x}
              tick={tick}
              axisLine={false}
              tickLine={false}
              width={ampliado ? 250 : 0}
              hide={!ampliado}
            />
            {tooltip}
            {legenda}
            {grafico.y.map((y, k) => (
              <Bar key={y} dataKey={y} name={nomeColuna(y)} fill={SERIES_CORES[k]} radius={[0, 4, 4, 0]} maxBarSize={24} barSize={ampliado ? undefined : 10}>
                {!ampliado && k === 0 && <LabelList dataKey={grafico.x} content={rotuloAcima} />}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
        {nota}
      </>
    );
  }

  const altura = ampliado ? 360 : 170;
  return (
    <>
      <ResponsiveContainer width="100%" height={altura}>
        {tipo === "linha" ? (
          <LineChart data={rows} margin={{ top: 6, right: 12, left: ampliado ? 0 : -18, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} vertical={false} />
            <XAxis dataKey={grafico.x} tick={tick} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={fmtEixo} />
            {tooltip}
            {legenda}
            {grafico.y.map((y, k) => (
              <Line
                key={y}
                type="monotone"
                dataKey={y}
                name={nomeColuna(y)}
                stroke={SERIES_CORES[k]}
                strokeWidth={2}
                dot={rows.length <= 12 ? { r: 4 } : false}
                activeDot={{ r: 5 }}
                connectNulls
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={rows} margin={{ top: 6, right: 8, left: ampliado ? 0 : -18, bottom: 0 }} barCategoryGap="20%">
            <CartesianGrid strokeDasharray="3 3" stroke={GRAY_100} vertical={false} />
            <XAxis
              dataKey={grafico.x}
              tick={tick}
              axisLine={false}
              tickLine={false}
              interval={ampliado && rows.length <= 40 ? 0 : "preserveStartEnd"}
              minTickGap={4}
              tickFormatter={rotulo(10)}
              angle={inclinar ? -35 : 0}
              textAnchor={inclinar ? "end" : "middle"}
              height={inclinar ? Math.min(110, 18 + maiorRotulo * 5) : 30}
            />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={fmtEixo} />
            {tooltip}
            {legenda}
            {grafico.y.map((y, k) => (
              <Bar key={y} dataKey={y} name={nomeColuna(y)} fill={SERIES_CORES[k]} radius={[4, 4, 0, 0]} maxBarSize={ampliado ? 36 : 22} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
      {nota}
    </>
  );
}

function GraficoChat({ grafico, colunas, dados }: { grafico: Grafico; colunas: string[]; dados: unknown[][] }) {
  const [ampliado, setAmpliado] = useState(false);

  useEffect(() => {
    if (!ampliado) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setAmpliado(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ampliado]);

  const titulo = grafico.titulo || `${nomeColuna(grafico.y[0])} por ${nomeColuna(grafico.x).toLowerCase()}`;
  const botao: CSSProperties = {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: BLUE,
    fontSize: 10.5,
    padding: 0,
    fontFamily: "inherit",
  };

  return (
    <div style={{ background: WHITE, border: `1px solid ${GRAY_200}`, borderRadius: 6, padding: "6px 6px 4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: GRAY_800 }}>{titulo}</span>
        <button type="button" onClick={() => setAmpliado(true)} style={botao}>
          Ampliar
        </button>
      </div>
      <GraficoCanvas grafico={grafico} colunas={colunas} dados={dados} ampliado={false} />

      {ampliado &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-label={titulo}
            onClick={() => setAmpliado(false)}
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 200,
              background: "rgba(30,36,64,0.45)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 16,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: WHITE,
                borderRadius: 12,
                boxShadow: SHADOW,
                width: "min(860px, 100%)",
                maxHeight: "90vh",
                overflowY: "auto",
                padding: "16px 20px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: GRAY_800 }}>{titulo}</span>
                <button type="button" onClick={() => setAmpliado(false)} style={{ ...botao, fontSize: 12 }}>
                  Fechar
                </button>
              </div>
              <GraficoCanvas grafico={grafico} colunas={colunas} dados={dados} ampliado />
            </div>
          </div>,
          // no body: fora do painel do chat (position: fixed + overflow), cobre a tela toda
          document.body,
        )}
    </div>
  );
}

function ResultadoPreview({ resultado }: { resultado: ChatResposta }) {
  // Valor único já está na resposta em texto; a tabela só ajuda com 2+ células.
  const temTabela = resultado.dados.length > 1 || resultado.colunas.length > 1;
  const restantes = resultado.total_linhas - PREVIEW_LINHAS;
  const cell: CSSProperties = { padding: "4px 6px", borderBottom: `1px solid ${GRAY_200}`, whiteSpace: "nowrap", textAlign: "left" };

  return (
    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
      {resultado.grafico && (
        <GraficoChat grafico={resultado.grafico} colunas={resultado.colunas} dados={resultado.dados} />
      )}
      {temTabela && (
        <div style={{ overflowX: "auto", background: WHITE, border: `1px solid ${GRAY_200}`, borderRadius: 6 }}>
          <table style={{ borderCollapse: "collapse", fontSize: 10.5, width: "100%" }}>
            <thead>
              <tr>
                {resultado.colunas.map((c) => (
                  <th key={c} style={{ ...cell, color: GRAY_600, fontWeight: 600 }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {resultado.dados.slice(0, PREVIEW_LINHAS).map((linha, i) => (
                <tr key={i}>
                  {linha.map((v, j) => (
                    <td key={j} style={cell}>{formatCell(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {restantes > 0 && (
            <div style={{ padding: "4px 6px", fontSize: 10, color: GRAY_400 }}>
              + {restantes}{resultado.truncado ? "+" : ""} linha(s)
            </div>
          )}
        </div>
      )}
      {resultado.sql && (
        <details style={{ fontSize: 10.5, color: GRAY_600 }}>
          <summary style={{ cursor: "pointer" }}>Ver consulta SQL</summary>
          <pre style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 10, background: WHITE, border: `1px solid ${GRAY_200}`, borderRadius: 6, padding: 6 }}>
            {resultado.sql}
          </pre>
        </details>
      )}
    </div>
  );
}

function ChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Olá! Sou o assistente de análise acadêmica. Pergunte sobre alunos, cursos, disciplinas, notas, evasão ou formação.",
    },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  async function send(text: string) {
    const pergunta = text.trim();
    if (!pergunta || typing) return;
    // Histórico para perguntas de acompanhamento ("e em 2023.1?"): sem a saudação e sem erros.
    const historico: HistoricoItem[] = messages
      .slice(1)
      .filter((m) => !m.erro)
      .map((m) => ({ role: m.role, text: m.text }));
    setMessages((prev) => [...prev, { role: "user", text: pergunta }]);
    setInput("");
    setTyping(true);
    try {
      const resultado = await perguntar(pergunta, historico);
      setMessages((prev) => [...prev, { role: "assistant", text: resultado.resposta, resultado }]);
    } catch (err) {
      const text = err instanceof Error ? err.message : "Erro inesperado ao consultar o assistente.";
      setMessages((prev) => [...prev, { role: "assistant", text, erro: true }]);
    } finally {
      setTyping(false);
    }
  }

  if (!open) return null;

  const avatarStyle: CSSProperties = {
    width: 24,
    height: 24,
    borderRadius: "50%",
    background: BLUE_LIGHT,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginRight: 8,
    marginTop: 2,
  };

  const botAvatar = (
    <div style={avatarStyle}>
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="5" r="2.5" stroke={BLUE} strokeWidth="1.8" />
        <path d="M2 13c0-2.5 2.5-4.5 6-4.5s6 2 6 4.5" stroke={BLUE} strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    </div>
  );

  return (
    <div
      className="chat-panel"
      style={{
        // Camada sobreposta: fica fora do fluxo do layout, então abrir/fechar
        // o chat não altera largura nem posição do dashboard.
        position: "fixed",
        top: 56,
        right: 0,
        width: 320,
        height: "calc(100vh - 56px)",
        zIndex: 90,
        background: WHITE,
        borderLeft: `1px solid ${GRAY_200}`,
        boxShadow: "-8px 0 24px rgba(30,36,64,0.10)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "14px 16px",
          borderBottom: `1px solid ${GRAY_200}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: "50%", background: BLUE, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 11.5C2 9 4 7 8 7s6 2 6 4.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx="8" cy="4" r="2.5" stroke="white" strokeWidth="1.5" />
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: GRAY_800, lineHeight: 1 }}>Assistente IA</div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e" }} />
              <span style={{ fontSize: 10, color: GRAY_400 }}>Online</span>
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Fechar assistente"
          style={{ background: "none", border: "none", cursor: "pointer", color: GRAY_400, padding: 4, borderRadius: 6, display: "flex", alignItems: "center" }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
            {msg.role === "assistant" && botAvatar}
            <div
              style={{
                // respostas com gráfico usam mais largura do painel
                maxWidth: msg.resultado?.grafico ? "88%" : "80%",
                flex: msg.resultado?.grafico ? 1 : undefined,
                padding: "9px 12px",
                borderRadius: msg.role === "user" ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
                background: msg.role === "user" ? BLUE : msg.erro ? RED_LIGHT : GRAY_50,
                color: msg.role === "user" ? WHITE : msg.erro ? RED : GRAY_800,
                fontSize: 12.5,
                lineHeight: 1.55,
                whiteSpace: "pre-wrap",
                minWidth: 0,
              }}
            >
              {msg.text}
              {msg.resultado && <ResultadoPreview resultado={msg.resultado} />}
            </div>
          </div>
        ))}
        {typing && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {botAvatar}
            <div style={{ background: GRAY_50, borderRadius: "12px 12px 12px 2px", padding: "9px 14px", display: "flex", gap: 4 }}>
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: GRAY_400,
                    animation: "bounce 1.2s infinite",
                    animationDelay: `${i * 0.2}s`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length === 1 && (
        <div style={{ padding: "0 14px 10px", display: "flex", flexDirection: "column", gap: 6, flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: GRAY_400, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
            Sugestões
          </div>
          {SUGESTOES.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              style={{
                background: GRAY_50,
                borderWidth: "1px",
                borderStyle: "solid",
                borderColor: GRAY_200,
                borderRadius: 8,
                padding: "7px 10px",
                fontSize: 11.5,
                color: BLUE,
                cursor: "pointer",
                textAlign: "left",
                fontFamily: "inherit",
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div style={{ padding: "12px 14px", borderTop: `1px solid ${GRAY_200}`, display: "flex", gap: 8, flexShrink: 0 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Faça uma pergunta..."
          style={{
            flex: 1,
            height: 36,
            padding: "0 12px",
            borderWidth: "1px",
            borderStyle: "solid",
            borderColor: GRAY_200,
            borderRadius: 8,
            fontSize: 12.5,
            color: GRAY_800,
            background: GRAY_50,
            outline: "none",
            fontFamily: "inherit",
          }}
        />
        <button
          onClick={() => send(input)}
          disabled={!input.trim() || typing}
          aria-label="Enviar"
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: input.trim() ? BLUE : GRAY_100,
            border: "none",
            cursor: input.trim() ? "pointer" : "default",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "background 0.15s",
            flexShrink: 0,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M2 8h12M9 3l5 5-5 5" stroke={input.trim() ? WHITE : GRAY_400} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── Root App ───────────────────────────────────────────────────────────────
export default function App() {
  const [data, setData] = useState<MinedData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeNav, setActiveNav] = useState("alunos");
  const [chatOpen, setChatOpen] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    loadMinedData()
      .then(setData)
      .catch((err) => setLoadError(err instanceof Error ? err.message : String(err)));
  }, []);

  const statusText = data
    ? `${data.alunosResumo.length.toLocaleString("pt-BR")} alunos · ${data.disciplinasRows.rows.length.toLocaleString("pt-BR")} matrículas`
    : loadError
      ? "Erro ao carregar dados"
      : "Carregando dados...";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: GRAY_50,
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
        color: GRAY_800,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          background: WHITE,
          borderBottom: `1px solid ${GRAY_200}`,
          padding: "0 20px",
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "sticky",
          top: 0,
          zIndex: 100,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => setSidebarCollapsed((v) => !v)}
            aria-label="Alternar menu lateral"
            style={{ background: "none", border: "none", cursor: "pointer", color: GRAY_400, padding: 4, borderRadius: 6, display: "flex" }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <rect x="2" y="4" width="14" height="1.6" rx="0.8" fill="currentColor" />
              <rect x="2" y="8.2" width="14" height="1.6" rx="0.8" fill="currentColor" />
              <rect x="2" y="12.4" width="14" height="1.6" rx="0.8" fill="currentColor" />
            </svg>
          </button>
          <InstitutionLogo />
          <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: GRAY_800, lineHeight: 1 }}>Sigadash.v2</div>
            <div style={{ fontSize: 10, color: GRAY_400, lineHeight: 1.5 }}>Monitoramento Acadêmico Institucional</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: data ? "#22c55e" : loadError ? RED : GRAY_400 }} />
          <span className="header-status" style={{ fontSize: 11, color: GRAY_400 }}>
            {statusText}
          </span>
        </div>
      </div>

      {/* ── Body ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Sidebar */}
        <div
          style={{
            width: sidebarCollapsed ? 56 : 220,
            flexShrink: 0,
            background: WHITE,
            borderRight: `1px solid ${GRAY_200}`,
            display: "flex",
            flexDirection: "column",
            transition: "width 0.2s ease",
            overflow: "hidden",
            height: "calc(100vh - 56px)",
            position: "sticky",
            top: 56,
          }}
        >
          {!sidebarCollapsed ? (
            <div style={{ padding: "16px 16px 8px", fontSize: 10, fontWeight: 700, color: GRAY_400, letterSpacing: "0.07em", textTransform: "uppercase" }}>
              Painéis
            </div>
          ) : (
            <div style={{ height: 24 }} />
          )}
          <nav style={{ display: "flex", flexDirection: "column", gap: 2, padding: "0 8px" }}>
            {NAV_ITEMS.map((item) => {
              const active = activeNav === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveNav(item.id)}
                  title={sidebarCollapsed ? item.label : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: sidebarCollapsed ? "10px 12px" : "9px 12px",
                    borderRadius: 8,
                    background: active ? BLUE_LIGHT : "transparent",
                    border: "none",
                    cursor: "pointer",
                    color: active ? BLUE : GRAY_600,
                    fontSize: 12.5,
                    fontWeight: active ? 600 : 400,
                    textAlign: "left",
                    width: "100%",
                    whiteSpace: "nowrap",
                    transition: "background 0.12s, color 0.12s",
                    fontFamily: "inherit",
                  }}
                >
                  <span style={{ flexShrink: 0 }}>{item.icon}</span>
                  {!sidebarCollapsed && <span>{item.label}</span>}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Main content */}
        <div style={{ flex: 1, overflowY: "auto", minWidth: 0 }}>
          {loadError && (
            <div style={{ padding: 24 }}>
              <Card>
                <div style={{ color: RED, fontWeight: 600, marginBottom: 6 }}>Erro ao carregar os dados minerados</div>
                <div style={{ fontSize: 13, color: GRAY_600 }}>{loadError}</div>
                <div style={{ fontSize: 12, color: GRAY_400, marginTop: 8 }}>
                  Os arquivos esperados ficam em <code>public/data/generated/</code> e são gerados por{" "}
                  <code>python python/run_mining.py</code>.
                </div>
              </Card>
            </div>
          )}
          {!loadError && !data && <div style={{ padding: 24, color: GRAY_400, fontSize: 13 }}>Carregando dados minerados...</div>}
          {!loadError && data && activeNav === "alunos" && <AlunasPanel data={data} />}
          {!loadError && data && activeNav === "disciplinas" && <DisciplinasPanel data={data} />}
        </div>

        {/* Chat */}
        {!chatOpen && (
          <button
            onClick={() => setChatOpen(true)}
            style={{
              position: "fixed",
              top: "50%",
              right: 0,
              transform: "translateY(-50%)",
              background: BLUE,
              color: WHITE,
              border: "none",
              cursor: "pointer",
              borderRadius: "8px 0 0 8px",
              padding: "10px 6px",
              fontSize: 10,
              fontWeight: 700,
              writingMode: "vertical-rl",
              letterSpacing: "0.05em",
              fontFamily: "inherit",
              zIndex: 90,
            }}
          >
            IA
          </button>
        )}
        <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
      </div>
    </div>
  );
}
