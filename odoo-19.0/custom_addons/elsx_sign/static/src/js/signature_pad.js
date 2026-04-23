odoo.define('elsx_sign.signature_pad', function (require) {
    "use strict";

    var publicWidget = require('web.public.widget');
    var ajax = require('web.ajax');

    publicWidget.registry.ElsxSignaturePad = publicWidget.Widget.extend({
        selector: '#elsx_signature_portal_app',
        events: {
            'click #action_clear_signature': '_onClearSignature',
            'click #action_submit_signature': '_onSubmitSignature',
            'mousedown #signature-pad': '_onDrawStart',
            'mousemove #signature-pad': '_onDrawMove',
            'mouseup window': '_onDrawEnd',
            'touchstart #signature-pad': '_onDrawStart',
            'touchmove #signature-pad': '_onDrawMove',
            'touchend document': '_onDrawEnd',
        },

        start: function () {
            var res = this._super.apply(this, arguments);
            this.canvas = this.$el.find('#signature-pad')[0];
            this.ctx = this.canvas.getContext('2d');
            this.isDrawing = false;
            
            // Adjust to visual size
            this.canvas.width = this.canvas.offsetWidth;
            this.canvas.height = this.canvas.offsetHeight;
            this.ctx.lineWidth = 3;
            this.ctx.lineCap = "round";
            this.ctx.strokeStyle = "#000";

            return res;
        },

        _getMousePos: function (evt) {
            var rect = this.canvas.getBoundingClientRect();
            if (evt.type.includes('touch')) {
                return {
                    x: evt.originalEvent.touches[0].clientX - rect.left,
                    y: evt.originalEvent.touches[0].clientY - rect.top
                };
            }
            return {
                x: evt.clientX - rect.left,
                y: evt.clientY - rect.top
            };
        },

        _onDrawStart: function (evt) {
            evt.preventDefault();
            this.isDrawing = true;
            var pos = this._getMousePos(evt);
            this.ctx.beginPath();
            this.ctx.moveTo(pos.x, pos.y);
        },

        _onDrawMove: function (evt) {
            if (!this.isDrawing) return;
            evt.preventDefault();
            var pos = this._getMousePos(evt);
            this.ctx.lineTo(pos.x, pos.y);
            this.ctx.stroke();
        },

        _onDrawEnd: function (evt) {
            if (this.isDrawing) {
                this.ctx.closePath();
                this.isDrawing = false;
            }
        },

        _onClearSignature: function () {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        },

        _onSubmitSignature: function (evt) {
            var $btn = $(evt.currentTarget);
            var requestId = $btn.data('request-id');
            var token = $btn.data('token');
            
            // Check if blank
            var blank = document.createElement('canvas');
            blank.width = this.canvas.width;
            blank.height = this.canvas.height;
            if (this.canvas.toDataURL() === blank.toDataURL()) {
                alert("Please draw your signature before submitting.");
                return;
            }

            var signatureData = this.canvas.toDataURL("image/png");
            
            $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Saving...');

            ajax.jsonRpc('/sign/submit_signature', 'call', {
                'request_id': requestId,
                'token': token,
                'signature_data': signatureData
            }).then(function (result) {
                if (result.success) {
                    window.location.reload();
                } else {
                    alert("Error: " + result.error);
                    $btn.prop('disabled', false).html('<i class="fa fa-check-circle"></i> Finalize & Sign');
                }
            });
        }
    });
});
