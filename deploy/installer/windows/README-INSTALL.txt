PreVeda Madhu-DR - installer
============================
1. Unzip this folder anywhere (for example C:\PreVeda).
2. Double-click  Install-PreVeda.bat
   - It checks for Docker and installs Docker Desktop if it is missing (Windows 10/11, internet needed once).
   - It starts Docker, builds the single container image, and runs it.
   - It asks nothing: all local drives are shared read-only with the app.
   - You then type the image folder (for example D:\Hospital\Fundus) in the web app: Settings -> Image folder.
   - It runs two things on two ports (if a default port is busy it picks the next free one):
        Web app   http://localhost:8081   -> sign in: doctor / doctor123 or admin / admin123
        REST API  http://localhost:8080/docs   (for other hospital systems / developers)
   - When ready, your browser opens the web app.
   - In the app: Settings -> Scan folder now, or turn on automatic scanning.
3. To stop:  Stop-PreVeda.bat   (saved results are kept in a Docker volume)

First install of Docker may ask you to restart Windows and to accept Docker's terms.
If so, do that, then double-click Install-PreVeda.bat again.

Notes
- Until you set a folder, the app reads the 'images' folder next to this file. Nothing is uploaded or changed.
- The demo logins are for a local trial only.
- Results are stored in the Docker volume 'madhu-data'. Auth is OFF by default (local trial only);
  set PREVEDA_AUTH_MODE and related settings before connecting real clinical users.
- Guideline wording (app\config\guidelines.json) is a DRAFT until your clinician approves it.
- This is a screening aid, not a diagnosis.
- Log of the installation: install.log
