"""
Algoritmo de projeção do notebook regress_copy_6.ipynb (célula 9), portado sem
alterações de lógica.

Ficaram de fora apenas as partes que não geram a projeção: avaliação
walk-forward (avaliar_walk_forward, avaliar_walk_forward_por_curso,
_ordenar_classes), feature_importances_transicao e os resumos de diagnóstico.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Hashable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer


class ClassificadorAcademico:
    """
    Projeção populacional de situação acadêmica via Random Forest de transição.

    Principais correções incorporadas:
      1. Períodos suspeitos não contaminam lags nem pares de transição.
      2. O treino usa somente transições reais entre períodos consecutivos.
      3. O último período observado não recebe "AUSENTE" artificialmente.
      4. A coorte futura contém somente alunos elegíveis.
      5. PERIODO_ADMIS é preservado na projeção.
      6. Ponderação por confiança altera de fato a contribuição populacional.
      7. A imputação numérica fica dentro do pipeline.
      8. O arredondamento preserva a soma inteira projetada.

    Fluxo:
      - periodo_alvo: período a projetar.
      - periodo_base: última coorte saudável anterior ao alvo.
      - períodos suspeitos são excluídos do treino e não entram nos lags.
      - o RF aprende P -> P+1 usando apenas transições consecutivas observadas.
      - a projeção é obtida pela soma das probabilidades individuais.
    """

    COLS_TEMPORAIS = [
        "NU_MEDIA_FIM",
        "NU_TOT_FALTAS",
        "qtd_periodos",
        "DS_SIT_HIST",
        "qtd_miss_media",
        "qtd_miss_faltas",
    ]

    MEDIA_MISS = {-2, -3, -4, -5, -6}
    FALTAS_MISS = {-1, -2, -3, -4}

    CAT_COLS = [
        "DS_SIT_HIST_lag1",
        "DS_SIT_HIST_lag2",
    ]

    NUM_COLS = [
        "PERIODO_ADMIS",
        "qtd_periodos_lag1",
        "qtd_periodos_lag2",
        "NU_MEDIA_FIM_lag1",
        "NU_MEDIA_FIM_lag2",
        "NU_TOT_FALTAS_lag1",
        "NU_TOT_FALTAS_lag2",
    ]

    FLAG_COLS = [
        "qtd_miss_media_lag1",
        "qtd_miss_media_lag2",
        "qtd_miss_faltas_lag1",
        "qtd_miss_faltas_lag2",
    ]

    COLUNAS_DESCARTAR = ["NM_PROGR_FORM", "NU_ANO_CONC", "NM_COMPNT_CURR"]
    STATUS_TERMINAIS_DEFAULT = ["CONCLUSÃO", "EVASÃO"]
    ESTADO_AUSENTE = "AUSENTE"
    FILL_FLAG = 0.0
    FILL_CAT = "SEM_HISTORICO"

    def __init__(
        self,
        target: str = "DS_TP_SIT_ACAD",
        coluna_id: str = "codigo_estudante",
        coluna_periodo: str = "CD_PERD_LETV",
        random_state: int = 42,
    ):
        self.target = target
        self.coluna_id = coluna_id
        self.coluna_periodo = coluna_periodo
        self.random_state = random_state

        self.tabela_bruta_ = None
        self.df_agregado_ = None
        self.periodos_letivos_ = None

        self.modelo_transicao_rf_ = None
        self.roll_forward_ = None
        self.diagnostico_periodos_ = None

    # =========================================================
    # 1. UTILIDADES DE PERÍODO
    # =========================================================

    @staticmethod
    def _chave_periodo(periodo: Hashable):
        """Chave estável para ordenar períodos acadêmicos comuns."""
        if periodo is None or (isinstance(periodo, float) and np.isnan(periodo)):
            return (9, "")

        if isinstance(periodo, (int, float, np.number)):
            valor = float(periodo)
            if valor.is_integer():
                texto = str(int(valor))
                m = re.fullmatch(r"(\d{4})(\d)", texto)
                if m:
                    return (0, int(m.group(1)), int(m.group(2)))
            else:
                # Algumas planilhas importam períodos como números decimais
                # (ex.: 2026.1) em vez de strings. Reconhece esse formato para
                # torná-lo equivalente a "2026.1" e ao inteiro codificado 20261.
                m = re.fullmatch(r"(\d{4})\.(\d)", str(periodo).strip())
                if m:
                    return (0, int(m.group(1)), int(m.group(2)))
            return (1, valor)

        s = str(periodo).strip()
        m = re.fullmatch(r"(\d{4})[.\-](\d)", s)
        if m:
            return (0, int(m.group(1)), int(m.group(2)))

        m = re.fullmatch(r"(\d{4})(\d)", s)
        if m:
            return (0, int(m.group(1)), int(m.group(2)))

        return (2, s)

    @staticmethod
    def _rotulo_periodo(periodo: Hashable) -> str:
        """Retorna um rótulo textual estável para exibir/consultar períodos."""
        chave = ClassificadorAcademico._chave_periodo(periodo)
        if len(chave) == 3 and chave[0] == 0:
            return f"{chave[1]}.{chave[2]}"
        if periodo is None:
            return "None"
        return str(periodo).strip()

    @staticmethod
    def _periodo_solicitado_corresponde(periodo: Hashable, solicitado: Hashable) -> bool:
        """Compara períodos aceitando formatos equivalentes e seleção por ano."""
        texto = str(solicitado).strip()
        # Um ano isolado (ex.: 2026) seleciona todos os semestres desse ano.
        if re.fullmatch(r"\d{4}", texto):
            chave = ClassificadorAcademico._chave_periodo(periodo)
            return len(chave) == 3 and chave[0] == 0 and chave[1] == int(texto)
        return (
            ClassificadorAcademico._chave_periodo(periodo)
            == ClassificadorAcademico._chave_periodo(solicitado)
        )

    def _ordenar_periodos(self, periodos) -> list:
        valores = list(pd.Series(list(periodos)).dropna().unique())
        return sorted(valores, key=self._chave_periodo)

    def _proximo_periodo_id(self, periodo_base) -> str:
        """Gera o identificador do semestre seguinte."""
        if isinstance(periodo_base, (int, float, np.number)):
            valor = float(periodo_base)
            if valor.is_integer():
                s = str(int(valor))
                m = re.fullmatch(r"(\d{4})(\d)", s)
                if m:
                    ano, sem = int(m.group(1)), int(m.group(2))
                    return f"{ano + 1}1" if sem >= 2 else f"{ano}{sem + 1}"
            return str(periodo_base + 1)

        s = str(periodo_base).strip()
        m = re.fullmatch(r"(\d{4})[.\-](\d)", s)
        if m:
            ano, sem = int(m.group(1)), int(m.group(2))
            return f"{ano + 1}.1" if sem >= 2 else f"{ano}.{sem + 1}"

        m = re.fullmatch(r"(\d{4})(\d)", s)
        if m:
            ano, sem = int(m.group(1)), int(m.group(2))
            return f"{ano + 1}1" if sem >= 2 else f"{ano}{sem + 1}"

        return f"{s}_PROX"

    def _mapa_sucessores(self, periodos) -> dict:
        ordenados = self._ordenar_periodos(periodos)
        return {
            atual: ordenados[i + 1]
            for i, atual in enumerate(ordenados[:-1])
        }

    def _mapa_predecessores(self, periodos) -> dict:
        ordenados = self._ordenar_periodos(periodos)
        return {
            ordenados[i]: ordenados[i - 1]
            for i in range(1, len(ordenados))
        }

    # =========================================================
    # 2. AGREGAÇÃO E ENGENHARIA DE FEATURES
    # =========================================================

    def _agregar_estudante_periodo(self, df: pd.DataFrame) -> pd.DataFrame:
        """Consolida a base no nível aluno-período e limpa sentinelas."""
        df_temp = df.copy()

        if "NU_MEDIA_FIM" in df_temp.columns:
            is_media_miss = df_temp["NU_MEDIA_FIM"].isin(self.MEDIA_MISS)
        else:
            is_media_miss = pd.Series(False, index=df_temp.index, dtype=bool)

        if "NU_TOT_FALTAS" in df_temp.columns:
            is_faltas_miss = df_temp["NU_TOT_FALTAS"].isin(self.FALTAS_MISS)
        else:
            is_faltas_miss = pd.Series(False, index=df_temp.index, dtype=bool)

        df_temp["qtd_miss_media"] = is_media_miss.astype(int)
        df_temp["qtd_miss_faltas"] = is_faltas_miss.astype(int)

        if "NU_MEDIA_FIM" in df_temp.columns:
            df_temp.loc[is_media_miss, "NU_MEDIA_FIM"] = np.nan
        if "NU_TOT_FALTAS" in df_temp.columns:
            df_temp.loc[is_faltas_miss, "NU_TOT_FALTAS"] = np.nan

        agg_dict = {
            "NU_MEDIA_FIM": "mean",
            "NU_TOT_FALTAS": "sum",
            "qtd_miss_media": "sum",
            "qtd_miss_faltas": "sum",
            "qtd_periodos": "max",
            "PERIODO_ADMIS": "first",
            self.target: "last",
            "DS_SIT_HIST": "last",
        }

        for col in df_temp.columns:
            if col in agg_dict:
                continue
            if col in (self.coluna_id, self.coluna_periodo) or col in self.COLUNAS_DESCARTAR:
                continue
            if pd.api.types.is_numeric_dtype(df_temp[col]):
                agg_dict[col] = "mean"
            else:
                agg_dict[col] = "last"

        agg_dict = {k: v for k, v in agg_dict.items() if k in df_temp.columns}

        return (
            df_temp.groupby([self.coluna_id, self.coluna_periodo], as_index=False)
            .agg(agg_dict)
        )

    def _reindexar_serie_temporal(self, df: pd.DataFrame) -> pd.DataFrame:
        """Uma linha por aluno e período global; usado apenas para construir lags/ausências."""
        if df.empty:
            return df

        chave = [self.coluna_id, self.coluna_periodo]
        df = df.drop_duplicates(subset=chave, keep="last").copy()

        periodos = self._ordenar_periodos(df[self.coluna_periodo].dropna().unique())
        alunos = df[self.coluna_id].dropna().unique()

        idx = pd.MultiIndex.from_product([alunos, periodos], names=chave)
        df_indexado = (
            df.set_index(chave)
            .reindex(idx)
            .reset_index()
        )

        df_indexado = df_indexado[
            df_indexado[self.coluna_id].notna()
        ].reset_index(drop=True)

        # PERIODO_ADMIS é atributo do aluno, não deve desaparecer nas linhas sintéticas.
        if "PERIODO_ADMIS" in df_indexado.columns:
            df_indexado["PERIODO_ADMIS"] = (
                df_indexado.groupby(self.coluna_id)["PERIODO_ADMIS"]
                .transform(lambda s: s.ffill().bfill())
            )

        return df_indexado

    def _preparar_caracteristicas(
        self,
        df_agregado: pd.DataFrame,
        periodos_bloqueados: set | None = None,
    ) -> pd.DataFrame:
        """Gera lags de 1 e 2 períodos sem atravessar períodos bloqueados."""
        if df_agregado is None or df_agregado.empty:
            return pd.DataFrame()

        periodos_bloqueados = set(periodos_bloqueados or [])
        df = self._reindexar_serie_temporal(df_agregado)
        df = df.sort_values([self.coluna_id, self.coluna_periodo]).reset_index(drop=True)

        df["_periodo_lag1"] = df.groupby(self.coluna_id)[self.coluna_periodo].shift(1)
        df["_periodo_lag2"] = df.groupby(self.coluna_id)[self.coluna_periodo].shift(2)

        for c in self.COLS_TEMPORAIS:
            if c not in df.columns:
                continue
            for k in (1, 2):
                df[f"{c}_lag{k}"] = df.groupby(self.coluna_id)[c].shift(k)

        # Um lag não pode atravessar uma quebra provocada por período suspeito.
        if periodos_bloqueados:
            m1 = df["_periodo_lag1"].isin(periodos_bloqueados)
            m2 = df["_periodo_lag2"].isin(periodos_bloqueados)
            for c in self.COLS_TEMPORAIS:
                col = f"{c}_lag1"
                if col in df.columns:
                    df.loc[m1, col] = np.nan
                col = f"{c}_lag2"
                if col in df.columns:
                    df.loc[m2, col] = np.nan

        return df

    @property
    def caracteristicas(self) -> list:
        return self.CAT_COLS + self.NUM_COLS + self.FLAG_COLS

    def _preencher_ausentes(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.FLAG_COLS:
            if col in df.columns:
                df[col] = df[col].fillna(self.FILL_FLAG)
        for col in self.CAT_COLS:
            if col in df.columns:
                df[col] = df[col].fillna(self.FILL_CAT)
        return df

    def _validar_features(self, df: pd.DataFrame, contexto: str = "") -> None:
        faltantes = [c for c in self.caracteristicas if c not in df.columns]
        if faltantes:
            raise ValueError(f"[{contexto}] Colunas de features ausentes: {faltantes}")

        cols_obj = df[self.caracteristicas].select_dtypes(
            include=["object", "category"]
        ).columns.tolist()
        fora_de_cat = [c for c in cols_obj if c not in self.CAT_COLS]
        if fora_de_cat:
            raise ValueError(
                f"[{contexto}] Colunas categóricas não declaradas em CAT_COLS: "
                f"{fora_de_cat}."
            )

    # =========================================================
    # 3. PIPELINE
    # =========================================================

    def _construir_pipeline_transicao(
        self,
        n_estimators: int = 500,
        max_depth: int = 12,
        min_samples_leaf: int = 10,
    ) -> Pipeline:
        """Pipeline com encoding categórico e imputação numérica."""
        pre = ColumnTransformer(
            [
                (
                    "cat",
                    OneHotEncoder(
                        handle_unknown="ignore",
                        min_frequency=0.01,
                    ),
                    self.CAT_COLS,
                ),
                (
                    "num",
                    SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                    self.NUM_COLS,
                ),
                (
                    "flag",
                    SimpleImputer(strategy="most_frequent"),
                    self.FLAG_COLS,
                ),
            ],
            remainder="drop",
        )

        clf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_leaf * 2,
            min_samples_leaf=min_samples_leaf,
            max_features="sqrt",
            class_weight=None,
            random_state=self.random_state,
            n_jobs=-1,
        )

        return Pipeline([("pre", pre), ("clf", clf)])

    # =========================================================
    # 4. DETECÇÃO DE PERÍODOS SUSPEITOS
    # =========================================================

    def detectar_periodos_suspeitos(
        self,
        limiar_queda: float = 0.5,
        janela_referencia: int = 3,
        min_absoluto: int | None = 100,
        periodos_suspeitos_manuais: list | None = None,
    ) -> pd.DataFrame:
        """Detecta períodos com volume anormalmente baixo."""
        if self.df_agregado_ is None:
            raise RuntimeError("Execute .preparar() primeiro.")

        contagem = (
            self.df_agregado_
            .dropna(subset=[self.target])
            .groupby(self.coluna_periodo)[self.coluna_id]
            .nunique()
        )

        contagem = contagem.reindex(self._ordenar_periodos(contagem.index))
        df = pd.DataFrame({"periodo": contagem.index, "n_alunos": contagem.values})

        df["mediana_referencia"] = (
            df["n_alunos"]
            .shift(1)
            .rolling(window=janela_referencia, min_periods=1)
            .median()
        )
        df["razao"] = df["n_alunos"] / df["mediana_referencia"]

        suspeito = df["razao"] < (1 - limiar_queda)
        if min_absoluto is not None:
            suspeito = suspeito | (df["n_alunos"] < min_absoluto)
        if periodos_suspeitos_manuais:
            suspeito = suspeito | df["periodo"].isin(periodos_suspeitos_manuais)

        df["suspeito"] = suspeito.fillna(False)
        self.diagnostico_periodos_ = df
        return df

    # =========================================================
    # 5. RESOLUÇÃO DE PERÍODOS
    # =========================================================

    def _resolver_periodos(
        self,
        periodo_base: Hashable | None,
        periodo_alvo: Hashable | None,
        limiar_queda: float,
        min_absoluto: int | None,
        periodos_suspeitos_manuais: list | None,
    ) -> dict:
        if self.df_agregado_ is None:
            raise RuntimeError("Execute .preparar() primeiro.")

        todos = self._ordenar_periodos(
            self.df_agregado_[self.coluna_periodo].dropna().unique()
        )
        if len(todos) < 3:
            raise ValueError("Base precisa ter ao menos 3 períodos.")

        df_diag = self.detectar_periodos_suspeitos(
            limiar_queda=limiar_queda,
            min_absoluto=min_absoluto,
            periodos_suspeitos_manuais=periodos_suspeitos_manuais,
        )
        suspeitos = set(df_diag.loc[df_diag["suspeito"], "periodo"])

        if periodo_alvo is None:
            if periodo_base is not None:
                periodo_alvo = self._proximo_periodo_id(periodo_base)
            else:
                saudaveis = [p for p in todos if p not in suspeitos]
                if not saudaveis:
                    raise ValueError("Nenhum período saudável encontrado.")
                periodo_alvo = self._proximo_periodo_id(saudaveis[-1])

        if periodo_base is not None and periodo_base in suspeitos:
            raise ValueError(
                f"O período-base {periodo_base!r} foi classificado como suspeito. "
                "Escolha uma coorte saudável."
            )

        candidatos = [
            p
            for p in todos
            if self._chave_periodo(p) < self._chave_periodo(periodo_alvo)
            and p not in suspeitos
        ]
        if periodo_base is None:
            if not candidatos:
                raise ValueError(
                    f"Nenhum período anterior a {periodo_alvo} disponível."
                )
            periodo_base = candidatos[-1]

        periodos_treino = [
            p
            for p in todos
            if self._chave_periodo(p) < self._chave_periodo(periodo_alvo)
            and p not in suspeitos
        ]

        if len(periodos_treino) < 2:
            raise ValueError(
                f"Após excluir suspeitos, sobraram {len(periodos_treino)} "
                "períodos para treino (mínimo: 2)."
            )

        periodos_excluidos = [
            p
            for p in todos
            if self._chave_periodo(p) < self._chave_periodo(periodo_alvo)
            and p in suspeitos
        ]

        return {
            "periodo_base": periodo_base,
            "periodo_alvo": periodo_alvo,
            "periodos_treino": periodos_treino,
            "periodos_excluidos": periodos_excluidos,
            "df_diagnostico": df_diag,
        }

    # =========================================================
    # 6. BASE DE TRANSIÇÃO
    # =========================================================

    def _construir_base_transicao(
        self,
        df_agregado: pd.DataFrame,
        periodos_validos: list | None = None,
        periodos_bloqueados: list | None = None,
    ) -> pd.DataFrame:
        """
        Constrói X = histórico em P e y = situação em P+1.

        A ausência do aluno no período seguinte vira AUSENTE somente quando
        existe um período seguinte real na série global. O último período
        observado não vira AUSENTE artificialmente.
        """
        bloqueados = set(periodos_bloqueados or [])
        df = self._preparar_caracteristicas(
            df_agregado,
            periodos_bloqueados=bloqueados,
        )
        if df.empty:
            return df

        df = df.sort_values([self.coluna_id, self.coluna_periodo]).reset_index(drop=True)
        df["_periodo_P1"] = df.groupby(self.coluna_id)[self.coluna_periodo].shift(-1)
        df["_situacao_P1_bruta"] = df.groupby(self.coluna_id)[self.target].shift(-1)

        sucessor = self._mapa_sucessores(df_agregado[self.coluna_periodo].dropna().unique())
        df["_periodo_P1_esperado"] = df[self.coluna_periodo].map(sucessor)

        df = df[df[self.target].notna()].copy()

        if periodos_validos is not None:
            df = df[df[self.coluna_periodo].isin(periodos_validos)].copy()

        # Só há transição quando P+1 é realmente o período imediatamente seguinte.
        df = df[
            df["_periodo_P1"].eq(df["_periodo_P1_esperado"])
            & df["_periodo_P1_esperado"].notna()
        ].copy()

        if bloqueados:
            df = df[
                ~df[self.coluna_periodo].isin(bloqueados)
                & ~df["_periodo_P1"].isin(bloqueados)
            ].copy()

        df["situacao_P1"] = df["_situacao_P1_bruta"].fillna(self.ESTADO_AUSENTE)

        return df.drop(
            columns=[
                "_periodo_P1",
                "_situacao_P1_bruta",
                "_periodo_P1_esperado",
                "_periodo_lag1",
                "_periodo_lag2",
            ],
            errors="ignore",
        )

    def _selecionar_elegiveis(
        self,
        df_agregado: pd.DataFrame,
        periodo_base: Hashable,
        status_terminais: list,
    ) -> pd.DataFrame:
        """Alunos do período-base que não são estados terminais."""
        base = df_agregado[
            (df_agregado[self.coluna_periodo] == periodo_base)
            & df_agregado[self.target].notna()
        ].copy()
        base = base[~base[self.target].isin(status_terminais)]
        base = base.drop_duplicates(subset=[self.coluna_id], keep="last")
        return base

    # =========================================================
    # 7. FEATURES DO LOTE FUTURO
    # =========================================================

    def _construir_features_futuro(
        self,
        df_agregado: pd.DataFrame,
        elegiveis: pd.DataFrame,
        periodo_base: Hashable,
        periodos_bloqueados: set | None = None,
    ) -> pd.DataFrame:
        """
        Monta diretamente as features para a coorte elegível.

        Isso evita o produto cartesiano do histórico com o futuro e garante
        que somente a coorte-base seja enviada ao predict_proba().
        """
        bloqueados = set(periodos_bloqueados or [])
        periodos = self._ordenar_periodos(df_agregado[self.coluna_periodo].dropna().unique())
        predecessores = self._mapa_predecessores(periodos)

        prev1 = predecessores.get(periodo_base)
        prev2 = predecessores.get(prev1) if prev1 is not None else None

        hist = df_agregado.drop_duplicates(
            subset=[self.coluna_id, self.coluna_periodo],
            keep="last",
        ).copy()
        hist = hist.set_index([self.coluna_id, self.coluna_periodo], drop=False)

        out = elegiveis[[self.coluna_id]].copy()

        # PERIODO_ADMIS é atributo estático do aluno.
        if "PERIODO_ADMIS" in elegiveis.columns:
            out["PERIODO_ADMIS"] = elegiveis["PERIODO_ADMIS"].values
        else:
            out["PERIODO_ADMIS"] = np.nan

        # lag1 = período-base; lag2 = período anterior à base.
        for c in self.COLS_TEMPORAIS:
            out[f"{c}_lag1"] = elegiveis[c].values if c in elegiveis.columns else np.nan

            valores_lag2 = []
            for aluno in elegiveis[self.coluna_id]:
                valor = np.nan
                if prev1 is not None and prev1 not in bloqueados:
                    try:
                        if (aluno, prev1) in hist.index:
                            valor = hist.loc[(aluno, prev1), c]
                    except KeyError:
                        pass
                valores_lag2.append(valor)
            out[f"{c}_lag2"] = valores_lag2

        out = self._preencher_ausentes(out)
        return out

    # =========================================================
    # 8. ESTIMATIVA DE INGRESSO
    # =========================================================

    def _estimar_ingresso_recente(
        self,
        df_agregado: pd.DataFrame,
        periodos_validos: list | None = None,
        janela: int = 4,
        metrica: str = "media",
    ) -> float:
        df = df_agregado.dropna(subset=[self.target]).copy()

        if df.empty:
            return 0.0

        primeiros = df.groupby(self.coluna_id)[self.coluna_periodo].min()
        ingressos_raw = primeiros.value_counts()

        periodos_disponiveis = self._ordenar_periodos(
            periodos_validos if periodos_validos is not None
            else df[self.coluna_periodo].dropna().unique()
        )
        if not periodos_disponiveis:
            return 0.0

        periodos_recentes = periodos_disponiveis[-janela:]
        ingressos = ingressos_raw.reindex(periodos_recentes, fill_value=0).astype(float)

        if metrica == "ultimo":
            return float(ingressos.iloc[-1])
        if metrica != "media":
            raise ValueError("metrica_ingresso deve ser 'media' ou 'ultimo'.")

        return float(ingressos.mean())

    # =========================================================
    # 9. ARREDONDAMENTO
    # =========================================================

    @staticmethod
    def _arredondar_preservando_soma(serie: pd.Series) -> pd.Series:
        """Arredonda valores não negativos preservando a soma inteira."""
        if serie.empty:
            return serie.astype(int)

        valores = serie.astype(float).clip(lower=0).to_numpy()
        pisos = np.floor(valores).astype(int)
        alvo = int(np.rint(valores.sum()))
        falta = alvo - int(pisos.sum())

        if falta > 0:
            frac = valores - pisos
            ordem = np.argsort(-frac)
            pisos[ordem[:falta]] += 1
        elif falta < 0:
            frac = valores - pisos
            ordem = np.argsort(frac)
            pisos[ordem[: -falta]] -= 1

        return pd.Series(pisos, index=serie.index, dtype=int)

    # =========================================================
    # 10. ROLL-FORWARD
    # =========================================================

    def prever_roll_forward(
        self,
        periodo_alvo: Hashable | None = None,
        periodo_base: Hashable | None = None,
        periodos_suspeitos_manuais: list | None = None,
        limiar_queda: float = 0.5,
        min_absoluto: int | None = 100,
        permitir_colisao: bool = False,
        janela_ingresso: int = 4,
        metrica_ingresso: str = "media",
        incluir_ingresso: bool = True,
        ponderar_por_confianca: bool = False,
        incluir_ausente: bool = False,
        status_terminais: list | None = None,
        n_estimators: int = 500,
        max_depth: int = 12,
        min_samples_leaf: int = 10,
    ) -> dict:
        """Projeta o período-alvo via RF de transição."""
        if self.df_agregado_ is None:
            raise RuntimeError("Execute .preparar() primeiro.")

        if status_terminais is None:
            status_terminais = list(self.STATUS_TERMINAIS_DEFAULT)

        df_agregado = self.df_agregado_

        resolucao = self._resolver_periodos(
            periodo_base=periodo_base,
            periodo_alvo=periodo_alvo,
            limiar_queda=limiar_queda,
            min_absoluto=min_absoluto,
            periodos_suspeitos_manuais=periodos_suspeitos_manuais,
        )

        periodo_base = resolucao["periodo_base"]
        periodo_alvo = resolucao["periodo_alvo"]
        periodos_treino = resolucao["periodos_treino"]
        periodos_excluidos = resolucao["periodos_excluidos"]

        # ---------------------------------------------------------
        # 1. Base de transição sem vazamento de períodos suspeitos
        # ---------------------------------------------------------
        df_trans = self._construir_base_transicao(
            df_agregado,
            periodos_validos=periodos_treino,
            periodos_bloqueados=periodos_excluidos,
        )

        if df_trans.empty:
            raise ValueError(
                f"Base de transição vazia para os períodos {periodos_treino}."
            )

        self._validar_features(df_trans, contexto="transicao_rf-treino")

        X_train = self._preencher_ausentes(df_trans[self.caracteristicas].copy())
        y_train = df_trans["situacao_P1"]

        if y_train.nunique() < 2:
            raise ValueError(
                "A base de transição possui apenas uma classe em situacao_P1; "
                "o Random Forest precisa de pelo menos duas classes."
            )

        rf_pipe = self._construir_pipeline_transicao(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
        )
        rf_pipe.fit(X_train, y_train)
        self.modelo_transicao_rf_ = rf_pipe

        classes_rf = list(rf_pipe.named_steps["clf"].classes_)

        # ---------------------------------------------------------
        # 2. Coorte elegível no período-base
        # ---------------------------------------------------------
        elegiveis = self._selecionar_elegiveis(
            df_agregado,
            periodo_base,
            status_terminais,
        )
        if elegiveis.empty:
            raise ValueError(f"Nenhum aluno elegível em {periodo_base}.")

        alvo_ja_existe = (df_agregado[self.coluna_periodo] == periodo_alvo).any()
        if alvo_ja_existe and not permitir_colisao:
            raise ValueError(
                f"O período-alvo {periodo_alvo!r} já existe em df_agregado_. "
                "Se for validação walk-forward, use permitir_colisao=True."
            )

        # Não utiliza linhas sintéticas nem produto cartesiano para o futuro.
        df_proximo = self._construir_features_futuro(
            df_agregado,
            elegiveis,
            periodo_base=periodo_base,
            periodos_bloqueados=set(periodos_excluidos),
        )

        self._validar_features(df_proximo, contexto="transicao_rf-projecao")
        X_elegiveis = self._preencher_ausentes(df_proximo[self.caracteristicas].copy())

        # ---------------------------------------------------------
        # 3. Probabilidades individuais
        # ---------------------------------------------------------
        probas = rf_pipe.predict_proba(X_elegiveis)

        if ponderar_por_confianca:
            pesos = probas.max(axis=1)
            contrib = probas * pesos[:, None]
        else:
            pesos = np.ones(probas.shape[0], dtype=float)
            contrib = probas

        contagens = pd.Series(
            contrib.sum(axis=0),
            index=classes_rf,
            dtype=float,
        )

        massa_total_antes_filtro = float(contagens.sum())

        if not incluir_ausente:
            contagens = contagens.drop(
                labels=[self.ESTADO_AUSENTE],
                errors="ignore",
            )

        # ---------------------------------------------------------
        # 4. Ingressos estimados
        # ---------------------------------------------------------
        ingresso_est = 0.0
        if incluir_ingresso:
            ingresso_est = self._estimar_ingresso_recente(
                df_agregado,
                periodos_validos=periodos_treino,
                janela=janela_ingresso,
                metrica=metrica_ingresso,
            )
            if ingresso_est > 0:
                if "ALUNOS ATIVOS" in contagens.index:
                    contagens["ALUNOS ATIVOS"] += ingresso_est
                else:
                    contagens.loc["ALUNOS ATIVOS"] = ingresso_est

        # ---------------------------------------------------------
        # 5. Arredondamento e resumo
        # ---------------------------------------------------------
        contagens_round = self._arredondar_preservando_soma(contagens)
        total = int(contagens_round.sum())

        if total > 0:
            proporcoes = (contagens_round / total).round(4)
        else:
            proporcoes = pd.Series(0.0, index=contagens_round.index)

        resumo_df = pd.DataFrame(
            {
                "quantidade_projetada": contagens_round,
                "proporcao_projetada": proporcoes,
            }
        ).sort_values("quantidade_projetada", ascending=False)

        # ---------------------------------------------------------
        # 6. Diagnósticos
        # ---------------------------------------------------------
        dist_base = (
            df_agregado[
                df_agregado[self.coluna_periodo] == periodo_base
            ][self.target]
            .value_counts()
        )
        n_por_classe_treino = y_train.value_counts().to_dict()

        previsoes_ind = pd.DataFrame(
            {
                self.coluna_id: elegiveis[self.coluna_id].values,
                **{
                    f"p_{c}": probas[:, i]
                    for i, c in enumerate(classes_rf)
                },
            }
        )
        previsoes_ind["confianca_maxima"] = probas.max(axis=1)
        previsoes_ind["peso_confianca"] = pesos

        self.roll_forward_ = {
            "metodo": "transicao_rf",
            "periodo_base": periodo_base,
            "periodo_alvo": periodo_alvo,
            "proximo_periodo_id": periodo_alvo,
            "periodos_usados_no_treino": self._ordenar_periodos(periodos_treino),
            "periodos_excluidos": self._ordenar_periodos(periodos_excluidos),
            "diagnostico_periodos": resolucao["df_diagnostico"],
            "n_pares_treino": len(df_trans),
            "n_elegiveis_base": len(elegiveis),
            "n_linhas_preditas": len(df_proximo),
            "distribuicao_treino_por_classe": n_por_classe_treino,
            "distribuicao_base": dist_base,
            "ingresso_estimado": round(ingresso_est, 2),
            "massa_probabilistica_antes_filtro_ausente": round(
                massa_total_antes_filtro, 6
            ),
            "total_alunos_projetados": total,
            "resumo_projetado": resumo_df,
            "modelo_transicao": rf_pipe,
            "previsoes_individuais": previsoes_ind,
        }

        return self.roll_forward_

    # =========================================================
    # 11. ORQUESTRAÇÃO
    # =========================================================

    def preparar(self, tabela: pd.DataFrame) -> "ClassificadorAcademico":
        self.tabela_bruta_ = tabela.copy()
        self.df_agregado_ = self._agregar_estudante_periodo(tabela)
        self.periodos_letivos_ = self._ordenar_periodos(
            self.df_agregado_[self.coluna_periodo].dropna().unique()
        )
        return self

    def run(
        self,
        tabela: pd.DataFrame,
        periodo_alvo: Hashable | None = None,
        periodos_suspeitos_manuais: list | None = None,
        **kwargs_roll_forward,
    ) -> dict:
        self.preparar(tabela)
        return self.prever_roll_forward(
            periodo_alvo=periodo_alvo,
            periodos_suspeitos_manuais=periodos_suspeitos_manuais,
            **kwargs_roll_forward,
        )

    def run_por_curso(
        self,
        tabela: pd.DataFrame,
        coluna_curso: str = "NM_PROGR_FORM",
        periodo_alvo: Hashable | None = None,
        periodos_suspeitos_manuais: list | None = None,
        diretorio_saida: str | Path = "resultados_por_curso",
        exportar_csv: bool = True,
        salvar_bases_cursos: bool = False,
        incluir_sem_curso: bool = False,
        limiar_queda: float = 0.5,
        min_absoluto: int | None = None,
        **kwargs_roll_forward,
    ) -> dict:
        """Treina um classificador independente para cada curso da tabela.

        A coluna indicada por ``coluna_curso`` é examinada automaticamente.
        Para cada curso distinto, o método cria um DataFrame filtrado, instancia
        uma nova ``ClassificadorAcademico`` e executa ``run()`` de forma isolada.

        Quando ``exportar_csv=True``, salva os DataFrames relevantes de cada
        projeção usando ``DataFrame.to_csv()``: resumo projetado, previsões
        individuais e diagnóstico de períodos. A tabela de entrada de cada curso
        também pode ser salva com ``salvar_bases_cursos=True``. Os arquivos são
        gravados em ``diretorio_saida`` e recebem o nome do curso no nome do
        arquivo. Um prefixo numérico evita colisões entre nomes semelhantes.

        ``min_absoluto`` usa ``None`` por padrão porque o limite original de 100
        alunos pode marcar todos os períodos de um curso pequeno como suspeitos.
        A detecção relativa de quedas continua ativa por meio de ``limiar_queda``.

        Parameters
        ----------
        tabela : pd.DataFrame
            Tabela histórica original, contendo a coluna de curso e as colunas
            necessárias para treinar o classificador.
        coluna_curso : str
            Coluna que identifica o curso. Padrão: ``"NM_PROGR_FORM"``.
        periodo_alvo : Hashable | None
            Período que será projetado. Se None, cada modelo resolve seu próprio
            próximo período-alvo com base no histórico daquele curso.
        periodos_suspeitos_manuais : list | None
            Períodos que devem ser tratados como suspeitos em todos os cursos.
        diretorio_saida : str | Path
            Pasta onde os arquivos CSV serão gravados.
        exportar_csv : bool
            Se True, exporta os DataFrames de saída de cada curso para CSV.
        salvar_bases_cursos : bool
            Se True, também exporta o DataFrame de entrada filtrado de cada curso.
        incluir_sem_curso : bool
            Se True, agrupa registros sem curso informado em ``SEM_CURSO``.
            Por padrão, esses registros são ignorados para não treinar um modelo
            sem identificação de curso.
        limiar_queda : float
            Limiar de queda usado na detecção de períodos suspeitos.
        min_absoluto : int | None
            Quantidade mínima de alunos para considerar um período saudável.
            O padrão None evita excluir automaticamente cursos pequenos.
        **kwargs_roll_forward
            Parâmetros adicionais encaminhados a ``prever_roll_forward()``,
            como ``n_estimators``, ``max_depth``, ``min_samples_leaf`` ou
            ``incluir_ingresso``.

        Returns
        -------
        dict
            Dicionário com ``dataframes_por_curso``, ``modelos_por_curso``,
            ``resultados_por_curso``, ``resumo_geral``, ``erros`` e
            ``arquivos_csv``. Um curso que falhar não impede a tentativa com os
            demais; a falha fica registrada em ``erros``.
        """
        if not isinstance(tabela, pd.DataFrame):
            raise TypeError("tabela deve ser um pandas.DataFrame.")
        if coluna_curso not in tabela.columns:
            raise KeyError(
                f"A coluna de cursos {coluna_curso!r} não existe na tabela."
            )
        if tabela.empty:
            raise ValueError("A tabela original está vazia.")

        df_trabalho = tabela.copy()
        # Usa uma coluna auxiliar para limpar espaços e agrupar valores sem
        # modificar o valor original da coluna de curso no DataFrame exportado.
        coluna_auxiliar = "__curso_chave_execucao__"
        while coluna_auxiliar in df_trabalho.columns:
            coluna_auxiliar = "_" + coluna_auxiliar

        chaves_curso = df_trabalho[coluna_curso].astype("string").str.strip()
        chaves_curso = chaves_curso.replace("", pd.NA)
        if incluir_sem_curso:
            chaves_curso = chaves_curso.fillna("SEM_CURSO")
        df_trabalho[coluna_auxiliar] = chaves_curso

        cursos = df_trabalho[coluna_auxiliar].dropna().drop_duplicates().tolist()
        if not cursos:
            raise ValueError(
                f"Nenhum curso válido foi encontrado na coluna {coluna_curso!r}."
            )

        pasta_saida = Path(diretorio_saida)
        if exportar_csv:
            pasta_saida.mkdir(parents=True, exist_ok=True)

        dataframes_por_curso = {}
        modelos_por_curso = {}
        resultados_por_curso = {}
        linhas_resumo_geral = []
        registros_erros = []
        arquivos_csv = []

        for numero, curso in enumerate(cursos, start=1):
            df_curso = (
                df_trabalho.loc[df_trabalho[coluna_auxiliar] == curso]
                .drop(columns=[coluna_auxiliar])
                .copy()
            )
            dataframes_por_curso[str(curso)] = df_curso

            nome_seguro = re.sub(r"[^\w.-]+", "_", str(curso), flags=re.UNICODE)
            nome_seguro = nome_seguro.strip("._")[:100] or "curso_sem_nome"
            prefixo = f"{numero:03d}_{nome_seguro}"

            try:
                modelo_curso = ClassificadorAcademico(
                    target=self.target,
                    coluna_id=self.coluna_id,
                    coluna_periodo=self.coluna_periodo,
                    random_state=self.random_state,
                )
                resultado_curso = modelo_curso.run(
                    df_curso,
                    periodo_alvo=periodo_alvo,
                    periodos_suspeitos_manuais=periodos_suspeitos_manuais,
                    limiar_queda=limiar_queda,
                    min_absoluto=min_absoluto,
                    **kwargs_roll_forward,
                )

                modelos_por_curso[str(curso)] = modelo_curso
                resultados_por_curso[str(curso)] = resultado_curso

                # Prepara resumo populacional para exportação e consolidação.
                resumo = resultado_curso.get("resumo_projetado")
                if isinstance(resumo, pd.DataFrame):
                    resumo_csv = resumo.copy().rename_axis("situacao").reset_index()
                    resumo_csv.insert(0, coluna_curso, str(curso))
                    resumo_csv.insert(1, "periodo_base", resultado_curso.get("periodo_base"))
                    resumo_csv.insert(2, "periodo_alvo", resultado_curso.get("periodo_alvo"))
                    linhas_resumo_geral.append(resumo_csv)
                    if exportar_csv:
                        caminho = pasta_saida / f"{prefixo}_resumo_projetado.csv"
                        resumo_csv.to_csv(caminho, index=False, encoding="utf-8-sig")
                        arquivos_csv.append(str(caminho))

                # Exporta as probabilidades/previsões individuais do curso.
                previsoes = resultado_curso.get("previsoes_individuais")
                if isinstance(previsoes, pd.DataFrame) and exportar_csv:
                    previsoes_csv = previsoes.copy()
                    previsoes_csv.insert(0, coluna_curso, str(curso))
                    previsoes_csv.insert(1, "periodo_base", resultado_curso.get("periodo_base"))
                    previsoes_csv.insert(2, "periodo_alvo", resultado_curso.get("periodo_alvo"))
                    caminho = pasta_saida / f"{prefixo}_previsoes_individuais.csv"
                    previsoes_csv.to_csv(caminho, index=False, encoding="utf-8-sig")
                    arquivos_csv.append(str(caminho))

                # Exporta o diagnóstico de períodos usado pelo modelo.
                diagnostico = resultado_curso.get("diagnostico_periodos")
                if isinstance(diagnostico, pd.DataFrame) and exportar_csv:
                    diagnostico_csv = diagnostico.copy()
                    diagnostico_csv.insert(0, coluna_curso, str(curso))
                    caminho = pasta_saida / f"{prefixo}_diagnostico_periodos.csv"
                    diagnostico_csv.to_csv(caminho, index=False, encoding="utf-8-sig")
                    arquivos_csv.append(str(caminho))

                if exportar_csv and salvar_bases_cursos:
                    caminho = pasta_saida / f"{prefixo}_base_curso.csv"
                    df_curso.to_csv(caminho, index=False, encoding="utf-8-sig")
                    arquivos_csv.append(str(caminho))

            except Exception as exc:
                # A execução prossegue para os outros cursos; a exceção fica
                # documentada para facilitar diagnóstico posterior.
                registros_erros.append(
                    {
                        coluna_curso: str(curso),
                        "n_linhas_base": int(len(df_curso)),
                        "tipo_erro": type(exc).__name__,
                        "erro": str(exc),
                    }
                )

        resumo_geral = (
            pd.concat(linhas_resumo_geral, ignore_index=True)
            if linhas_resumo_geral
            else pd.DataFrame(
                columns=[coluna_curso, "periodo_base", "periodo_alvo", "situacao",
                         "quantidade_projetada", "proporcao_projetada"]
            )
        )
        erros_df = pd.DataFrame(registros_erros)
        arquivos_df = pd.DataFrame({"arquivo_csv": arquivos_csv})

        if exportar_csv:
            if not resumo_geral.empty:
                caminho = pasta_saida / "resumo_projetado_todos_os_cursos.csv"
                resumo_geral.to_csv(caminho, index=False, encoding="utf-8-sig")
                arquivos_csv.append(str(caminho))
            if not erros_df.empty:
                caminho = pasta_saida / "erros_por_curso.csv"
                erros_df.to_csv(caminho, index=False, encoding="utf-8-sig")
                arquivos_csv.append(str(caminho))
            arquivos_df = pd.DataFrame({"arquivo_csv": arquivos_csv})

        return {
            "dataframes_por_curso": dataframes_por_curso,
            "modelos_por_curso": modelos_por_curso,
            "resultados_por_curso": resultados_por_curso,
            "resumo_geral": resumo_geral,
            "erros": erros_df,
            "arquivos_csv": arquivos_df,
        }
