# Exemplo: "SN2: the Walden inversion" (vitrine de trajetória reativa)

[English](README.md) · **Português**

![SN2: a inversão de Walden](media/sn2_walden.gif)

Vídeo narrado em inglês, de 26 s, da reação Cl⁻ + CH₃Br → ClCH₃ + Br⁻ em água. O cloreto ataca o carbono pelo lado oposto ao bromo (ataque pela retaguarda), a ligação C–Cl se forma enquanto a C–Br se alonga, o grupo CH₃ passa por um estado de transição planar e vira como um guarda-chuva, e o Br⁻ sai. **Cada átomo segue uma trajetória quântica real**, e as distâncias de ligação na tela são medidas nela. Vídeo: [`media/sn2_walden_1080p.mp4`](media/sn2_walden_1080p.mp4).

Render final: 1920×1080, Cycles 32 spp + OpenImageDenoise, motion blur. QA de áudio: −16,2 LUFS, pico verdadeiro −1,43 dBTP. Feito depois que a prévia em baixa resolução foi aprovada na revisão humana (G2).

## O cálculo
- **Método:** GFN2-xTB (tblite 0.7) com água implícita ALPB. O sistema tem Cl⁻ + CH₃Br + 40 águas explícitas, com uma parede harmônica para manter o aglomerado unido.
- **Estado de transição (TS):** varredura relaxada de ξ = d(C–Br) − d(C–Cl); o máximo foi confirmado como ponto de sela por **uma frequência imaginária**.
- **Solvente:** equilibrado por 1 ps a 300 K com as distâncias do TS fixas.
- **Dinâmica:** 12 trajetórias disparadas do TS para frente e para trás no tempo (NVE, passo de 0,5 fs); 2 foram reativas, e uma foi escolhida para o vídeo.
- **Tempo na tela:** câmera lenta em torno do TS, com relógio em fs. A curva de energia é qualitativa (nenhum valor de energia é citado).
- **Transparência:** a reação é um evento raro a 300 K. A trajetória mostrada foi lançada a partir do estado de transição (transition-path shooting, técnica padrão), e o vídeo declara isso na tela.

### Eventos calculados (detectados por código, tempo relativo ao TS)
| Evento | Definição | Tempo (fs) |
|---|---|---|
| approach | d(C–Cl) < 4,0 Å | −196 |
| backside | ângulo Cl–C–Br > 150° | −115 |
| ts | ξ cruza o máximo da varredura | +1 |
| flip | inversão do guarda-chuva: C cruza o plano H₃ | +18 |
| bond | d(C–Cl) < 2,0 Å após o TS | +36 |
| leave | d(C–Br) > 3,0 Å após o TS | +52 |

Os arquivos são os mesmos descritos no [README em inglês](README.md). A trajetória (`traj.npz`) não fica no repositório; veja [`md/DATA_README.md`](md/DATA_README.md).
