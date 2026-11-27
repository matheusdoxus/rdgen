#!/usr/bin/env python3
"""Botão "Pedir suporte" no app de acesso remoto da Doxus (RustDesk 1.5.3, modo "incoming only").

O botão fica no painel da esquerda, logo abaixo da senha de uso único. Ele abre uma janelinha (nome e problema)
e manda para a função pedir-suporte do Doxus CRM: o ID deste PC, a senha de uso único, o nome do PC e o texto.
O pedido cai na fila "Suporte remoto" do CRM e o técnico recebe um aviso no WhatsApp.

A chave do app vem da variável SUPORTE_APP_CHAVE (segredo do repositório no GitHub). A URL pode ser trocada com
SUPORTE_URL. Sem a chave o patch para com erro (não gera app sem o botão por engano).

O patch é idempotente (marcador DOXUS-PEDIR-SUPORTE) e para com erro se o código do RustDesk mudar.

Uso:
    python pedirSuporte.py [--rustdesk-root PATH]
"""

import argparse
import os
import pathlib
import re
import sys

MARCADOR = "// DOXUS-PEDIR-SUPORTE"
URL_PADRAO = "https://ttzshkxturtzklvmgtbr.supabase.co/functions/v1/pedir-suporte"

BOTAO_NO_PAINEL_ANTES = "      if (!isOutgoingOnly) buildPasswordBoard(context),\n"
BOTAO_NO_PAINEL_DEPOIS = (
    BOTAO_NO_PAINEL_ANTES
    + f"      if (!isOutgoingOnly) buildPedirSuporte(context), {MARCADOR}\n"
)

IMPORT_ANTES = "import 'package:flutter/material.dart';\n"
IMPORT_DEPOIS = "import 'package:http/http.dart' as http; " + MARCADOR + "\n" + IMPORT_ANTES

ANCORA_METODOS = "  buildRightPane(BuildContext context) {\n"

METODOS = r'''
  // DOXUS-PEDIR-SUPORTE: botão e janelinha do "Pedir suporte".
  static const _kPedirSuporteUrl = '__URL__';
  static const _kPedirSuporteChave = '__CHAVE__';

  Widget buildPedirSuporte(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(left: 20, right: 16, top: 14, bottom: 6),
      width: double.infinity,
      child: ElevatedButton.icon(
        icon: const Icon(Icons.support_agent, size: 20),
        label: const Text('Pedir suporte',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
        onPressed: () => _abrirPedirSuporte(context),
      ),
    );
  }

  void _abrirPedirSuporte(BuildContext context) {
    final nome = TextEditingController(
        text: bind.mainGetLocalOption(key: 'doxus-suporte-nome'));
    final problema = TextEditingController();
    var enviando = false;
    var enviado = false;
    String? erro;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setDialog) {
        Future<void> enviar() async {
          final n = nome.text.trim();
          if (n.isEmpty) {
            setDialog(() => erro = 'Escreva seu nome.');
            return;
          }
          setDialog(() {
            enviando = true;
            erro = null;
          });
          try {
            await bind.mainSetLocalOption(key: 'doxus-suporte-nome', value: n);
            final model = gFFI.serverModel;
            final meuId = await bind.mainGetMyId();
            var versao = '';
            try {
              versao = await bind.mainGetVersion();
            } catch (_) {}
            final resp = await http
                .post(
                  Uri.parse(_kPedirSuporteUrl),
                  headers: {
                    'Content-Type': 'application/json',
                    'x-suporte-chave': _kPedirSuporteChave,
                  },
                  body: jsonEncode({
                    'rustdesk_id': meuId,
                    'senha': model.serverPasswd.text,
                    'nome': n,
                    'problema': problema.text.trim(),
                    'nome_pc': Platform.localHostname,
                    'versao': versao,
                  }),
                )
                .timeout(const Duration(seconds: 25));
            if (resp.statusCode == 200) {
              setDialog(() {
                enviando = false;
                enviado = true;
              });
            } else {
              var msg = 'Não deu para enviar agora. Tente de novo.';
              try {
                final j = jsonDecode(utf8.decode(resp.bodyBytes));
                if (j is Map && j['error'] is String) msg = j['error'];
              } catch (_) {}
              setDialog(() {
                enviando = false;
                erro = msg;
              });
            }
          } catch (_) {
            setDialog(() {
              enviando = false;
              erro = 'Sem internet ou servidor fora do ar. Tente de novo.';
            });
          }
        }

        if (enviado) {
          return AlertDialog(
            title: const Text('Pedido enviado'),
            content: const SizedBox(
              width: 340,
              child: Text(
                  'A Doxus já recebeu seu pedido e vai conectar neste computador em instantes.\n\n'
                  'Deixe este programa aberto.'),
            ),
            actions: [
              ElevatedButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('Ok'),
              ),
            ],
          );
        }

        return AlertDialog(
          title: const Text('Pedir suporte'),
          content: SizedBox(
            width: 340,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: nome,
                  autofocus: nome.text.isEmpty,
                  maxLength: 80,
                  decoration: const InputDecoration(
                      labelText: 'Seu nome', counterText: ''),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: problema,
                  autofocus: nome.text.isNotEmpty,
                  maxLength: 500,
                  minLines: 3,
                  maxLines: 5,
                  decoration: const InputDecoration(
                      labelText: 'O que está acontecendo?',
                      alignLabelWithHint: true,
                      counterText: ''),
                ),
                if (erro != null) ...[
                  const SizedBox(height: 10),
                  Text(erro!, style: const TextStyle(color: Colors.red)),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: enviando ? null : () => Navigator.of(ctx).pop(),
              child: const Text('Cancelar'),
            ),
            ElevatedButton(
              onPressed: enviando ? null : enviar,
              child: enviando
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Enviar pedido'),
            ),
          ],
        );
      }),
    );
  }

'''


def substituir_uma_vez(texto: str, antes: str, depois: str, nome: str) -> str:
    n = texto.count(antes)
    if n != 1:
        sys.exit(f"pedirSuporte: esperava achar 1 vez '{nome}', achei {n}. O RustDesk mudou?")
    return texto.replace(antes, depois)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rustdesk-root", default=".")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    chave = os.environ.get("SUPORTE_APP_CHAVE", "").strip()
    url = os.environ.get("SUPORTE_URL", "").strip() or URL_PADRAO
    if not re.fullmatch(r"[A-Za-z0-9_]{16,128}", chave):
        sys.exit("pedirSuporte: falta SUPORTE_APP_CHAVE (segredo do repositório) ou ela tem caracteres estranhos.")
    if not re.fullmatch(r"https://[A-Za-z0-9./_-]+", url):
        sys.exit("pedirSuporte: SUPORTE_URL inválida.")

    arq = pathlib.Path(args.rustdesk_root) / "flutter/lib/desktop/pages/desktop_home_page.dart"
    texto = arq.read_text(encoding="utf-8")
    if MARCADOR in texto:
        print("pedirSuporte: já aplicado.")
        return

    texto = substituir_uma_vez(texto, IMPORT_ANTES, IMPORT_DEPOIS, "import material")
    texto = substituir_uma_vez(texto, BOTAO_NO_PAINEL_ANTES, BOTAO_NO_PAINEL_DEPOIS, "buildPasswordBoard no painel")
    metodos = METODOS.replace("__URL__", url).replace("__CHAVE__", chave)
    texto = substituir_uma_vez(texto, ANCORA_METODOS, metodos + ANCORA_METODOS, "buildRightPane")

    arq.write_text(texto, encoding="utf-8", newline="")
    print("pedirSuporte: botão Pedir suporte aplicado.")


if __name__ == "__main__":
    main()
