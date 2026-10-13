# MGE Skills

[English](README.md) · **Português**

Skills de agente para química computacional e divulgação científica, criadas durante trabalho
real de pesquisa. Cada pasta é uma skill independente (um `SKILL.md` com referências, modelos e
scripts) que o Claude Code, ou qualquer agente que leia `SKILL.md`, pode carregar.

| Skill | O que faz |
|---|---|
| [`molecular-motion-video`](molecular-motion-video/) | Vídeos narrados de motion graphics, cientificamente corretos, sobre moléculas, materiais e reações (Blender/Cycles). **Os átomos se movem segundo cálculos reais**: trajetórias de dinâmica molecular, caminhos de reação IRC/NEB e modos normais. Também cuida de narração local verificada em qualquer idioma, legendas palavra a palavra, rótulos guiados por dados, etapas de aprovação humana e conferência automática. |

Novas skills entram como subpastas.

## Instalação (Claude Code)

```bash
git clone https://github.com/MrGoulart3/MGE-Skills.git ~/MGE-Skills
~/MGE-Skills/install.sh                          # liga todas as skills em ~/.claude/skills/
~/MGE-Skills/install.sh molecular-motion-video   # ou só uma
```

Para atualizar: `git -C ~/MGE-Skills pull` (os links simbólicos acompanham).

## Princípios comuns
- **Ciência real primeiro:** geometria de dados cristalográficos ou calculados, movimento vindo de
  cálculos de fato, e cada afirmação listada com a fonte e validada por uma pessoa.
- **Do barato ao caro, com aprovação humana:** prévias antes de renders e cálculos finais.
- **Conferido com números:** cada etapa tem um modo de checagem que imprime o que o revisor precisa.

## Licença
MIT (veja `LICENSE`).
