首頁頁尾（出題、主辦、協辦與技術支持單位）的 logo。這裡的 PNG 是產生出來的，不要手改：

  backend/.venv/Scripts/python frontend/scripts/make_logos.py [--preview 預覽.png]

原始檔放在 repo 根目錄 Logo/（不進 git），對應關係寫在 make_logos.py 的 LOGOS：

  land.png       新北市政府地政局
  ntpc.png       新北市政府
  youth.png      新北市政府青年局
  digitimes.png  DIGITIMES
  netron.png     網創資訊 NETRON
  aws.png        AWS

處理方式：白底／黑底去背（標誌內被圍住的大塊白色保留，例如地政局的手）、
文字部分的黑灰轉白、彩色部分保留原色、裁到內容外框、高度上限 180 px。
頁面上各張的顯示高度在 features-c.css 的 .f-credits .cr-logo 個別調。
換 logo：換 Logo/ 裡的原始檔（或改 LOGOS 的檔名）後重跑，再 npm run build。
