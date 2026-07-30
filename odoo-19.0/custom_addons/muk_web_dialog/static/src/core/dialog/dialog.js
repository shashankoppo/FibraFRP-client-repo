import { session } from '@web/session';
import { patch } from '@web/core/utils/patch';

import { Dialog } from '@web/core/dialog/dialog';

function isWebsiteEditorContext() {
    const path = window.location.pathname || '';
    const body = document.body;
    return (
        path.includes('/@/') ||
        path.includes('/website/') ||
        Boolean(document.querySelector('.o_we_website_top_actions, .o_we_customize_panel, .o_we_snippets')) ||
        body?.classList.contains('editor_enable') ||
        body?.classList.contains('editor_has_snippets') ||
        body?.classList.contains('editor_has_snippets_hide_backend_navbar')
    );
}

patch(Dialog.prototype, {
  setup() {
    super.setup();
    const initialSize = this.props?.size || 'lg';
    this.data.initalSize = initialSize;
    if (isWebsiteEditorContext()) {
        this.data.size = initialSize;
        this.data.disableMukSizeToggle = true;
        return;
    }
    this.data.disableMukSizeToggle = false;
    this.data.size = (
        session.dialog_size !== 'maximize' ? initialSize : 'fs'
    );
  },
  onClickDialogSizeToggle() {
      if (this.data.disableMukSizeToggle) {
          return;
      }
      this.data.size = this.data.size === 'fs' ? this.data.initalSize : 'fs';
  }
});
