from odoo import models, fields, api
import logging
import random

_logger = logging.getLogger(__name__)

class ELSXMarketingAI(models.Model):
    _name = 'elsx.marketing.ai'
    _description = 'ELSX Generative Marketing AI'

    name = fields.Char('Campaign Name', required=True)
    target_audience = fields.Char('Target Audience')
    generated_content = fields.Text('AI Generated Content')
    platform = fields.Selection([
        ('email', 'Email'),
        ('linkedin', 'LinkedIn'),
        ('twitter', 'Twitter'),
        ('instagram', 'Instagram')
    ], string='Platform', default='email')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generating', 'Generating'),
        ('approved', 'Approved'),
        ('posted', 'Posted')
    ], default='draft')

    def action_generate_content(self):
        """Simulates AI content generation using templates/LLM logic."""
        self.state = 'generating'
        # In a real integration, this would call OpenAI/Gemini API
        # For now, we use high-quality ELSX templates
        
        templates = {
            'email': [
                "Subject: Unlock the Future with ELSX\n\nDear {Customer},\n\nExperience the next generation of ERP. ELSX utilizes self-evolving technology to keep your business ahead of the curve. Join the revolution today.",
                "Subject: Exclusive Access: ELSX Quantum Tier\n\nHi,\n\nWe've noticed you're ready for more. Upgrade to ELSX Quantum and tap into autonomous market research and blockchain security."
            ],
            'linkedin': [
                "🚀 Just upgraded our entire stack with ELSX ERP. The self-evolution engine is a game changer! #ELSX #TechRevolution #ERP",
                "Why settle for manual updates? ELSX updates itself. 🤖✨ #Automation #FutureofWork"
            ],
            'twitter': [
                "ELSX ERP is not just software, it's a living organism. 🌱 #Tech #AI",
                "Gone are the days of manual patching. Hello ELSX! 👋 #CyberpunkTech"
            ]
        }
        
        selected_template = random.choice(templates.get(self.platform, ['Generic Content']))
        self.generated_content = selected_template
        self.state = 'approved'
        _logger.info(f"ELSX AI Generated content for {self.name}")

    def action_post_content(self):
        """Simulates posting content."""
        self.state = 'posted'
        _logger.info(f"ELSX AI Posted content to {self.platform}")
