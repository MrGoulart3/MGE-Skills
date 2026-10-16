# Exemplo: "Salt dissolving" (vitrine de movimento calculado)

[English](README.md) · **Português**

![Sal dissolvendo](media/salt_dissolving.gif)

Vídeo narrado em inglês, de 28 s, em que um nanocristal de NaCl se dissolve em água. **Cada átomo segue uma trajetória real de dinâmica molecular**, não uma animação por keyframes. Render final (v2, 1920×1080, Cycles com denoiser e motion blur), feito depois que a prévia em baixa resolução foi aprovada na revisão humana (G2). Vídeo: [`media/salt_dissolving_1080p.mp4`](media/salt_dissolving_1080p.mp4).

Mudanças da v2 após a revisão: rótulos δ−/δ+ maiores e fora da água em destaque, câmera que acompanha essa água no close, e close no Cl⁻ que sai com o resto do cristal escurecido.

## O que mostra
1. Um cristal de sal em água.
2. A rede de Na⁺/Cl⁻.
3. Uma molécula polar de água (δ−/δ+).
4. A orientação da água na borda do cristal (O → Na⁺, H → Cl⁻).
5. Íons saindo com suas camadas de hidratação.
6. Cartela "Dissolving", com NaCl(s) → Na⁺(aq) + Cl⁻(aq).

Um relógio na tela mostra o tempo **simulado** (picossegundos), deixando explícita a compressão temporal.

## O cálculo
| Item | Valor |
|---|---|
| Motor | OpenMM 8.6 (CPU) |
| Campo de força | Água TIP3P, íons Joung–Cheatham (`amber14/tip3p.xml`) |
| Sistema | NaCl 4×4×4 (64 íons) + 2113 águas (6403 átomos) em caixa cúbica de 40,2 Å |
| Eletrostática e integração | PME, 2 fs, água rígida |
| Protocolo | minimização → NVT 300 K (100 ps) → NPT 1 bar (150 ps) → **produção NVT 400 K** (300 ps, 1 frame/ps) |
| Aceleração declarada | Temperatura elevada para a dissolução caber em ~10² ps. TIP3P também superestima a difusão. |
| Eventos detectados por código | Primeiro Cl⁻ sai aos 44 ps, depois mais 6 íons até 198 ps; hidratação na primeira camada ≈ 6 águas |

O pós-processamento (`md/fix_traj.py`) faz quatro operações:
- desdobra a trajetória no tempo;
- mantém as moléculas inteiras;
- escolhe **uma** imagem periódica fixa por água, próxima dos íons que ela hidrata;
- centraliza o quadro nos íons menos móveis.

## Arquivos
| Caminho | Conteúdo |
|---|---|
| `SCRIPT.md` | Roteiro, cenas A–F (eventos de narração) e tabela de afirmações científicas (G1) |
| `narration.json` | Frases + palavras-chave para `scripts/tts_verified.py` (6/6 tomadas verificadas pelo Whisper) |
| `timing/` | `timing.json`, `words.json`, `captions.srt` de `scripts/build_timing.py` |
| `MD_SPEC.md` | Contrato de dados da dinâmica molecular (em português) |
| `md/md_sal.py`, `md/post.py` | Simulação OpenMM e pós-processamento inicial |
| `md/fix_traj.py`, `md/events.json`, `md/DATA_README.md` | Preparação final dos dados, eventos calculados e notas |
| `md/fake_traj.py` | Trajetória sintética com o mesmo contrato, para desenvolver a cena antes de concluir a MD |
| `DIRECTION.md`, `ITERACAO_SAL2.md` | Direção e iteração de revisão com correções orientadas pela rubrica |
| `scene/sal_en.py`, `scene/style.json` | Cena Blender 4.2: malhas de pontos + Geometry Nodes, handler `frame_change_pre`, solução numérica da câmera e `--check` baseado nos dados |
| `post/montar_sal.py` | Legendas, rótulos, relógio MD e título (Pillow + ffmpeg), com música atenuada durante a voz |

As trajetórias (`traj.npz`, cerca de 14 MB cada) não são armazenadas aqui. Execute novamente `md/md_sal.py` e depois `md/fix_traj.py`.

## Lições registradas na skill
- Ao gravar keyframes de câmera guiada por `frame_change_pre`, reaplique a pose após `frame_set()`: as F-curves existentes a sobrescrevem. Adicione uma checagem após a gravação.
- Mostre apenas a água próxima do objeto (camada de ≈ 7,5 Å, desaparecendo até 12 Å) e oculte águas entre câmera e objeto. Milhares de moléculas viram ruído visual.
- Calibre os limites de `--check` com dados reais: a hidratação flutua a cada ps; use uma janela de mediana.

## Execute no seu ambiente

Execute a partir da pasta deste exemplo, no ambiente de cálculo, TTS ou render apropriado
(veja o README do repositório). Para regenerar a trajetória, execute dentro de `md/`:

```bash
MMV_THREADS=4 python3 md_sal.py 400 300 1
python3 post.py prod_raw.npz .
mv traj.npz traj_raw.npz
python3 fix_traj.py
```

Os três argumentos são temperatura de produção (K), tempo máximo de produção (ps) e escala
de equilibração (`1` para equilibração completa). `NT` tem precedência sobre `MMV_THREADS` por
compatibilidade; o padrão é 4 threads. Os parâmetros científicos acima reproduzem este exemplo;
para outro sistema, escolha novos parâmetros e valide os resultados.

De volta à pasta do exemplo, sintetize a narração e reconstrua os tempos:

```bash
python3 ../../scripts/tts_verified.py --script narration.json --out narration --lang en
python3 ../../scripts/build_timing.py --narration narration --out timing \
  --scenes A=1 B=2 C=3 D=4 E=5 F=6 \
  --events reveal=1:salt label_ions=2:sodium charges=2:charges \
  delta_minus=3:negative delta_plus=3:positive orient=4:oxygens \
  detach=5:free shell=5:shell title=6:dissolving
blender -b -t 4 -P scene/sal_en.py -- --check --threads 4
blender -b -t 4 -P scene/sal_en.py -- --preview --threads 4
```

A cena lê `md/` e `timing/`, escreve `anchors.json` na raiz do exemplo e salva os quadros em
`render/sal_en/<modo>/`. Depois de renderizar todos os quadros de um modo aprovado, monte-os:

```bash
python3 post/montar_sal.py --quadros render/sal_en/motion --saida preview.mp4 --procs 2
```

`montar_sal` monta o vídeo do sal; `--quadros` seleciona a entrada, `--saida` a saída e `--teste`
verifica o compositor, exigindo tempos, narração e âncoras reais. Use `--motion` para a prévia
completa em baixa resolução, obtenha G2 e então use `--final`. Se necessário, defina `FONT` e
`SYMBOL_FONT` para fontes instaladas (padrões: DejaVu Sans regular/negrito). As ferramentas de mídia
usam o `PATH` ou `FFMPEG`/`FFPROBE`; `MUSIC` adiciona opcionalmente uma trilha licenciada. Sem
`MUSIC`, o vídeo contém apenas narração. Não são necessários recursos privados nem nome fixo de ambiente conda.
