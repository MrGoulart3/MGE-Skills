# Exemplo: "Salt dissolving" (vitrine de movimento calculado)

[English](README.md) · **Português**

![Sal dissolvendo](media/salt_dissolving.gif)

Vídeo narrado em inglês, de 28 s, em que um nanocristal de NaCl se dissolve em água. **Cada átomo segue uma trajetória real de dinâmica molecular**, não uma animação por keyframes. Render final (v2, 1920×1080, Cycles com denoiser e motion blur), feito depois que a prévia em baixa resolução foi aprovada na revisão humana (G2). Vídeo: [`media/salt_dissolving_1080p.mp4`](media/salt_dissolving_1080p.mp4).

Mudanças da v2 após a revisão: rótulos δ−/δ+ maiores e fora da água em destaque, câmera que acompanha essa água no close, e close no Cl⁻ que sai com o resto do cristal escurecido.

## O cálculo
- **Simulação:** OpenMM 8.6 com água TIP3P e íons de Joung–Cheatham. O sistema tem NaCl 4×4×4 e 2113 águas, numa caixa de 40,2 Å, com PME e passo de 2 fs.
- **Protocolo:** equilibração a 300 K, depois **produção a 400 K** por 300 ps. A temperatura elevada acelera a dissolução, e isso é declarado.
- **Eventos detectados por código:** o primeiro Cl⁻ sai aos 44 ps, com cerca de 6 águas na 1ª camada.
- **Tempo na tela:** um relógio mostra o tempo simulado.

Os arquivos são os mesmos descritos no [README em inglês](README.md). As trajetórias (`traj.npz`) não ficam no repositório; rode `md/md_sal.py` e depois `md/fix_traj.py`.
