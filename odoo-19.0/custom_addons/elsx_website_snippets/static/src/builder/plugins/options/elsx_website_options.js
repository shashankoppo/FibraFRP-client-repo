import { BaseOptionComponent } from "@html_builder/core/utils";
import { END } from "@html_builder/utils/option_sequence";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";

const ELSX_SECTION_SELECTOR = [
    ".s_elsx_logo_cloud",
    ".s_elsx_logo_slider",
    ".s_elsx_testimonials",
    ".s_elsx_case_studies",
    ".s_elsx_stats",
    ".s_elsx_industries",
    ".s_elsx_faq",
    ".s_elsx_cta",
    ".s_elsx_process",
    ".s_elsx_comparison",
    ".s_elsx_brochure",
    ".s_elsx_trust_badges",
].join(", ");

export class ElsxWebsiteSectionOption extends BaseOptionComponent {
    static template = "elsx_website_snippets.ElsxWebsiteSectionOption";
    static selector = ELSX_SECTION_SELECTOR;
}

export class ElsxLogoSliderOption extends BaseOptionComponent {
    static template = "elsx_website_snippets.ElsxLogoSliderOption";
    static selector = ".s_elsx_logo_slider";
}

class ElsxWebsiteOptionsPlugin extends Plugin {
    static id = "elsxWebsiteOptions";
    resources = {
        builder_options: [
            withSequence(END, ElsxWebsiteSectionOption),
            withSequence(END, ElsxLogoSliderOption),
        ],
    };
}

registry.category("website-plugins").add(ElsxWebsiteOptionsPlugin.id, ElsxWebsiteOptionsPlugin);
