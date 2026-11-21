---
name: stark-rights
description: Verifica direitos de uso antes de editar/publicar (próprio, licença, permissão do criador, CC-BY, domínio público). Use ao receber vídeo de terceiro ou link do YouTube.
---

# stark-rights

1. Link do YouTube não é autorização. Download do YouTube viola os Termos (exceto o seu via YouTube Studio).
2. Exija base legal + titular + evidência (contrato, e-mail, licença, programa de clipadores). Registre: `POST $API/videos/<ID>/rights {"rights_type":"…","holder":"…","evidence":"…","allows_commercial":bool,"confirm":true}`.
3. Sem `allows_commercial`, não use em conta monetizada. CC-BY exige atribuição na legenda.
4. Programas de cortes (criador paga por views) = caminho legítimo p/ conteúdo de terceiros.
