/* Script inline (roda antes da hidratação): guarda o beforeinstallprompt para o botão "Instalar". */
export const BIP_SCRIPT =
  "window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();window.__starkBip=e;" +
  "window.dispatchEvent(new Event('stark-bip'))});window.addEventListener('appinstalled',function(){" +
  "window.__starkBip=null;window.__starkInstalled=true;window.dispatchEvent(new Event('stark-bip'))});";
