"""Gera o icone.ico da janela. Roda so quando o desenho muda.

Pillow e usado aqui, nao no app: o .ico fica versionado e o assistente so
carrega o arquivo pronto.

    python gerar_icone.py
"""
import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(BASE, "icone.ico")

FUNDO = (18, 18, 28, 255)      # mesmo fundo da janela
CARTAO = (45, 45, 66, 255)
TAMANHOS = [256, 128, 64, 48, 32, 16]
# as tres faixas de urgencia da interface: vencido, perto, tranquilo
FAIXAS = [(247, 118, 142, 255), (255, 158, 100, 255), (158, 226, 106, 255)]


def desenhar(lado):
    """Tres cartoes empilhados, cada um com sua faixa de urgencia - o mesmo
    desenho da lista de atividades."""
    escala = 8  # desenha grande e reduz, pra suavizar as bordas
    t = lado * escala
    img = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([0, 0, t - 1, t - 1], radius=int(t * 0.22), fill=FUNDO)

    margem = t * 0.16
    largura = t - 2 * margem
    altura_cartao = t * 0.17
    espaco = t * 0.075
    topo = (t - (3 * altura_cartao + 2 * espaco)) / 2
    raio = altura_cartao * 0.32
    faixa_larg = max(escala, largura * 0.085)

    for i, cor in enumerate(FAIXAS):
        y = topo + i * (altura_cartao + espaco)
        d.rounded_rectangle([margem, y, margem + largura, y + altura_cartao],
                            radius=raio, fill=CARTAO)
        # faixa colorida na esquerda, como nos cartoes da janela
        d.rounded_rectangle([margem + largura * 0.07, y + altura_cartao * 0.2,
                             margem + largura * 0.07 + faixa_larg, y + altura_cartao * 0.8],
                            radius=faixa_larg / 2, fill=cor)
        # tracinho representando o texto
        d.rounded_rectangle([margem + largura * 0.24, y + altura_cartao * 0.36,
                             margem + largura * 0.78, y + altura_cartao * 0.64],
                            radius=altura_cartao * 0.14, fill=(90, 90, 120, 255))

    return img.resize((lado, lado), Image.LANCZOS)


if __name__ == "__main__":
    imagens = [desenhar(t) for t in TAMANHOS]
    imagens[0].save(SAIDA, format="ICO", sizes=[(t, t) for t in TAMANHOS])
    print("gerado:", SAIDA)
