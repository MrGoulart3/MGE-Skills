# Exemplo: "SN2: the Walden inversion" (vitrine de trajetória reativa)

[English](README.md) · **Português**

![SN2: a inversão de Walden](media/sn2_walden.gif)

Vídeo narrado em inglês, de 26 s, da reação Cl⁻ + CH₃Br → ClCH₃ + Br⁻ em água. O cloreto ataca o carbono pelo lado oposto ao bromo (ataque pela retaguarda), a ligação C–Cl se forma enquanto a C–Br se alonga, o grupo CH₃ passa por um estado de transição planar e vira como um guarda-chuva, e o Br⁻ sai. **Cada átomo segue uma trajetória quântica real**, e as distâncias de ligação na tela são medidas nela. Vídeo: [`media/sn2_walden_1080p.mp4`](media/sn2_walden_1080p.mp4).

Render final: 1920×1080, Cycles 32 spp + OpenImageDenoise, motion blur. QA de áudio: −16,2 LUFS, pico verdadeiro −1,43 dBTP. Feito depois que a prévia em baixa resolução foi aprovada na revisão humana (G2).

## O que mostra
1. Reagentes em água: Cl⁻ e CH₃Br com algumas águas.
2. Aproximação e alinhamento pela retaguarda (Cl–C–Br próximo de 180°).
3. Estado de transição: carbono compartilhado entre Cl e Br, três hidrogênios no plano.
4. Formação e quebra de ligações, com distâncias C–Cl e C–Br lidas da trajetória.
5. Inversão de guarda-chuva do CH₃ (inversão de Walden).
6. Saída de Br⁻ e produto ClCH₃.

Um relógio de femtossegundos mostra o tempo **simulado**, com câmera lenta em torno do TS. Uma pequena curva de energia é qualitativa (sem valores de energia citados).

## O cálculo
| Item | Valor |
|---|---|
| Motor | GFN2-xTB via tblite 0.7, água implícita ALPB |
| Sistema | Cl⁻ + CH₃Br + 40 águas explícitas, com parede harmônica para manter o aglomerado unido |
| Busca do TS | Varredura relaxada de ξ = d(C–Br) − d(C–Cl); o máximo foi confirmado como ponto de sela por **uma frequência imaginária** |
| Solvente | Equilibrado por 1 ps a 300 K com as distâncias do TS fixas |
| Dinâmica | 12 trajetórias disparadas do TS para frente e para trás no tempo (NVE, passo de 0,5 fs); 2 foram reativas, e uma foi escolhida para o vídeo |
| Mapeamento temporal | Câmera lenta em torno do TS, com relógio em fs na tela |

**Transparência:** a reação é um evento raro a 300 K. A trajetória mostrada foi lançada a partir do estado de transição (transition-path shooting, técnica padrão), e o vídeo declara isso na tela ("launched from the transition state").

### Eventos calculados (detectados por código, tempo relativo ao cruzamento do TS)
| Evento | Definição | Tempo (fs) |
|---|---|---|
| approach | d(C–Cl) < 4,0 Å | −196 |
| backside | ângulo Cl–C–Br > 150° | −115 |
| ts | ξ cruza o máximo da varredura | +1 |
| flip | inversão do guarda-chuva: C cruza o plano H₃ e permanece | +18 |
| bond | d(C–Cl) < 2,0 Å após o TS | +36 |
| leave | d(C–Br) > 3,0 Å após o TS | +52 |

## Arquivos
| Caminho | Conteúdo |
|---|---|
| `SCRIPT.md` | Roteiro, tabela de cenas e afirmações científicas (G1) |
| `DIRECTION.md` | Direção para implementação da cena |
| `narration.json` | Frases + palavras-chave para `scripts/tts_verified.py` |
| `calc/ts_scan.py`, `calc/shoot.py`, `calc/make_traj.py` | Varredura e verificação de frequências do TS, disparos a partir dele e conversão ao contrato de trajetória da skill |
| `calc/scan.json`, `calc/ts_freq.txt` | Resultados da varredura e frequências do TS |
| `md/events.json`, `md/DATA_README.md` | Eventos calculados e regeneração dos dados |
| `scene/sn2_en.py`, `scene/style.json` | Cena Blender (reprodução da trajetória, ligações por distância e câmera) |
| `post/montar_sn2.py` | Legendas, rótulos, relógio em fs, gráfico de energia e título (Pillow + ffmpeg) |
| `media/` | Vídeo final 1080p, pôster e GIF |

A trajetória (`traj.npz`) não fica no repositório. Veja [`md/DATA_README.md`](md/DATA_README.md).

## Execute no seu ambiente

Regenere os dados calculados conforme [`md/DATA_README.md`](md/DATA_README.md). Na pasta deste
exemplo, use o ambiente TTS para gerar narração e tempos (tempos/áudio não são versionados):

```bash
python3 ../../scripts/tts_verified.py --script narration.json --out narration --lang en
python3 ../../scripts/build_timing.py --narration narration --out timing \
  --scenes A=1 B=2 C=3 D=4 E=5 F=6 \
  --events reveal=1:reaction clock=1:femtosecond label_cl=2:chloride label_me=2:methyl \
  axis=2:opposite bonds=3:bond ts=4:top flat=4:flat flip=5:flip leave=5:bromide \
  title=6:reaction:end
blender -b -t 4 -P scene/sn2_en.py -- --check --threads 4
blender -b -t 4 -P scene/sn2_en.py -- --preview --threads 4
```

A cena lê `md/` e `timing/`, escreve `anchors.json` na raiz do exemplo e salva quadros em
`render/sn2_en/<modo>/`. Use `--motion` para a prévia completa em baixa resolução, monte-a,
obtenha G2 e então use `--final`. No ambiente de render:

```bash
python3 post/montar_sn2.py --quadros render/sn2_en/motion --saida preview.mp4 --procs 2
python3 post/montar_sn2.py --teste --procs 2
```

`montar_sn2` monta o vídeo de SN2; `--quadros` seleciona a entrada, `--saida` a saída e `--teste`
verifica o compositor com dados sintéticos (exige tempos gerados e a varredura). Se necessário,
defina `FONT`/`SYMBOL_FONT` (padrões: DejaVu Sans regular/negrito) e opcionalmente `MUSIC` para
uma trilha licenciada. `FFMPEG`/`FFPROBE` substituem os executáveis do `PATH`. Threads, processos
e local de execução são escolhas suas; não são necessários recursos privados nem ambiente conda particular.
