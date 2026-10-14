# Exemplo: "Salt dissolving" (vitrine de movimento calculado)

[English](README.md) · **Português**

![Sal dissolvendo — prévia](media/salt_dissolving.gif)

Vídeo narrado em inglês, de 28 s, em que um nanocristal de NaCl se dissolve em água. **Cada átomo segue uma trajetória real de dinâmica molecular**, não uma animação por keyframes. Esta é a prévia em baixa resolução (640×360) aprovada na etapa de revisão humana (G2). Vídeo: [`media/salt_dissolving_preview.mp4`](media/salt_dissolving_preview.mp4).

## O cálculo
- **Simulação:** OpenMM 8.6 com água TIP3P e íons de Joung–Cheatham. O sistema tem NaCl 4×4×4 e 2113 águas, numa caixa de 40,2 Å, com PME e passo de 2 fs.
- **Protocolo:** equilibração a 300 K, depois **produção a 400 K** por 300 ps. A temperatura elevada acelera a dissolução, e isso é declarado.
- **Eventos detectados por código:** o primeiro Cl⁻ sai aos 44 ps, com cerca de 6 águas na 1ª camada.
- **Tempo na tela:** um relógio mostra o tempo simulado.

Os arquivos são os mesmos descritos no [README em inglês](README.md). As trajetórias (`traj.npz`) não ficam no repositório; rode `md/md_sal.py` e depois `md/fix_traj.py`.
