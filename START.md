# Start des Korrekturassistenten

1. Öffnen Sie PowerShell im Ordner `C:\BS\App-Dev-Space\Korrekturassistent`.
2. Installieren Sie einmalig die PDF-Bibliothek: `py -3 -m pip install PyMuPDF`.
3. Starten Sie `start_korrekturassistent.bat`.
4. Melden Sie sich für die KI-Funktion einmalig mit `codex login` in einer Konsole bei Ihrem ChatGPT-Plus-Konto an.

Die Anwendung erzeugt ihre Projekt- und Korrekturdaten lokal im Unterordner `data`.

Für die KI-Bewertung wird nur der Text anonymisierter OCR-PDFs zusammen mit Klausur und Erwartungshorizont an Codex übergeben. Original-PDFs und Namenszuordnungen gehören nicht zu diesem Projekt.
