// The text layouts of the airship screen: one table for the page (web/js/gameui.js draws them) and the mod (tools/ship_ui.py writes a .twui.xml of
// each; tools/ship_ui_config.mjs carries the table there). docs/design/port-to-game.md, 3.1: «Одна таблица стилей текста».
// Page fields: size in units of the game's interface (the game's points x 4/3), colour, bold, italic, align, valign, nowrap, line (the line's height),
// font ('header' or the body font). Game fields: cat, the game's font category (the face), and pt, the font size the layout gives it (font_m_size);
// a category marked unproven: true has not been seen working in this mod's layouts yet (the game's own templates use it).
// Colour: the game draws every text of a layout in the font's light colour (#FFF8D7) whatever font_m_colour says (runs/20261115-012811-ship_panel: the
// copper header, the brown ink, the grey captions all came out light); a layout gets another colour only by preset: the key of a row of the game's
// ui_colours table (font_colour_override_preset_key, as building_information.twui.xml greys its description), and colour is that row's colour,
// so the page draws what the game will. The [[col:...]] tags of a text take the same keys (GAME_COLOURS).
// The page's fonts stand in for the game's: a serif.
export const TEXT = {
    text_title: {size: 32, colour: '#FFF8D7', bold: true, align: 'center', nowrap: true, font: 'header', cat: 'header_24_bold', pt: 24},
    text_head: {size: 24, colour: '#FFE77F', preset: 'help_page_link_inactive', bold: true, nowrap: true, font: 'header', cat: 'header_18_bold', pt: 18},
    text_name: {size: 18.67, colour: '#FFF8D7', nowrap: true, font: 'header', cat: 'header_14', pt: 14},
    // a button's label, centred: a layout the mod does not have yet (tools/crew_ui.py: text_layout(..., "Center", "Never split"))
    // the number of men on a unit card (land_unit_card, unit_strength_number): small, centred
    // the numbers on a unit card (land_unit_card.twui.xml): the men and the cost body_10, the turns of a recruitment body_12; on the screen 13 and 16 px
    text_card_number: {size: 13, colour: '#FFF8D7', align: 'center', nowrap: true, cat: 'body_10', pt: 10, unproven: true},
    text_card_cost: {size: 13, colour: '#FFF8D7', nowrap: true, cat: 'body_10', pt: 10, unproven: true},
    text_card_turns: {size: 16, colour: '#FFF8D7', nowrap: true, cat: 'body_12', pt: 12},
    // the game's building information window (ui/campaign ui/building_information.twui.xml): the title header_14 centred, the chain's name and the
    // description body_12 centred (the description italic), the entries body_12. Colours as the game draws them (docs/feedback/01-building-tooltip.png):
    // the title #FFF8D7, the chain's name and the description dimmer, effects green, a reason red.
    // Sizes: the game's font sizes are points, 12 is 16 px and 14 is 19 px on the screen, lines 22 px apart (measured on that screenshot, which is 1:1:
    // its window is 400 wide as the template's). Every layout here is at the game's own size on the screen: a point of the game's font is 4/3 of a
    // unit (body_12 = 16, header_14 = 19, header_18 = 24, header_24 = 32); nothing is drawn smaller than the game draws it.
    text_info_title: {size: 19, colour: '#FFF8D7', align: 'center', nowrap: true, font: 'header', cat: 'header_14', pt: 14},
    text_info_centre: {size: 16, line: 22, colour: '#A99F89', preset: 'ui_font_faded_grey_beige', align: 'center', valign: 'top', cat: 'body_12', pt: 12},
    text_info_italic: {size: 16, line: 22, colour: '#A99F89', preset: 'ui_font_faded_grey_beige', align: 'center', valign: 'top', italic: true, cat: 'body_12_italic', pt: 12, unproven: true},
    text_info: {size: 16, line: 22, colour: '#FFF8D7', valign: 'top', cat: 'body_12', pt: 12},
    // a short caption under a card, centred, two lines at most
    // (16 px, the game's body size on the screen: at the scale the page has on a screen, about 0.6, it is still 10 px)
    text_caption: {size: 16, line: 20, colour: '#FFF8D7', align: 'center', valign: 'top', cat: 'body_12', pt: 12},
    text_caption_grey: {size: 16, line: 20, colour: '#A99F89', preset: 'ui_font_faded_grey_beige', align: 'center', valign: 'top', cat: 'body_12', pt: 12},
    text_caption_left: {size: 16, colour: '#FFF8D7', nowrap: true, cat: 'body_12', pt: 12},
    text_caption_copper: {size: 16, colour: '#FFE77F', preset: 'help_page_link_inactive', align: 'right', nowrap: true, cat: 'body_12', pt: 12},
    // the game's unit information panel (ui/common ui/unit_information.twui.xml): the name header_14 centred, the rest body_12, the notes body_10;
    // on the screen 19, 16 and 13 px, as the building information window
    text_unit_title: {size: 19, colour: '#FFF8D7', align: 'center', nowrap: true, font: 'header', cat: 'header_14', pt: 14},
    text_unit: {size: 16, colour: '#FFF8D7', nowrap: true, cat: 'body_12', pt: 12},
    text_unit_right: {size: 16, colour: '#FFF8D7', nowrap: true, align: 'right', cat: 'body_12', pt: 12},
    text_unit_centre: {size: 16, colour: '#FFF8D7', nowrap: true, align: 'center', cat: 'body_12', pt: 12},
    // the notes (a crew's description, the ammunition's share, the bonuses): body_12 as the rest of the panel. They were body_10 (13 units), which
    // the game draws 11 to 13 px high at a root of 1920 x 1080 (runs/20261115-012811-ship_panel): smaller than any text the player reads in the
    // game's own windows
    text_unit_note: {size: 16, line: 20, colour: '#FFF8D7', valign: 'top', cat: 'body_12', pt: 12},
    text_button: {size: 18.67, colour: '#FFF8D7', align: 'center', nowrap: true, font: 'header', cat: 'header_14', pt: 14},
    text_name_grey: {size: 18.67, colour: '#A99F89', preset: 'ui_font_faded_grey_beige', nowrap: true, font: 'header', cat: 'header_14', pt: 14},
    text_body: {size: 16, line: 20, colour: '#FFF8D7', valign: 'top', cat: 'body_12', pt: 12},
    text_line: {size: 16, colour: '#FFF8D7', nowrap: true, cat: 'body_12', pt: 12},
    text_line_grey: {size: 16, colour: '#A99F89', preset: 'ui_font_faded_grey_beige', nowrap: true, cat: 'body_12', pt: 12},
    text_copper: {size: 16, colour: '#FFE77F', preset: 'help_page_link_inactive', nowrap: true, cat: 'body_12', pt: 12},
    text_note: {size: 16, line: 20, colour: '#A99F89', preset: 'ui_font_faded_grey_beige', valign: 'top', cat: 'body_12', pt: 12},
    // ink on the parchment, for the turns written on the drawing: a layout the mod does not have yet (tools/crew_ui.py would get it)
    text_ink: {size: 20, colour: '#4D3019', preset: 'ui_font_brown', bold: true, nowrap: true, font: 'header', align: 'center', cat: 'header_14', pt: 15},
    // the count of the units folded into the plate «+N» over a slot of the tree (the card's number, larger)
    text_card_more: {size: 16, colour: '#FFF8D7', bold: true, align: 'center', nowrap: true, cat: 'body_12', pt: 12},
    text_green: {size: 16, line: 20, colour: '#A0FF37', preset: 'green', valign: 'top', cat: 'body_12', pt: 12},
    // the development points a level costs, on the teal round by its slot (building_frame.twui.xml, dev_points > dy_num_points_required): header_14
    // centred in the game's light colour with its black outline (text_outline_t0), red when the horde has too few
    text_points: {size: 18.67, colour: '#FFF8D7', align: 'center', nowrap: true, font: 'header', outline: true, cat: 'header_14', pt: 14},
};

// The rows of the game's ui_colours table (db.pack, db/ui_colours_tables) a text of this screen uses, as [[col:key]] tags and as a layout's preset:
// any other key the game draws in the layout's own colour (the first session's [[col:grey]] and [[col:game_red]] came out light). Their colours
// are the table's (red, green, blue); web/css/page.css .col_<key> draws the same.
export const GAME_COLOURS = {
    green: '#A0FF37', red: '#FF2D2D', yellow: '#FFB900', white: '#FFFFFF', fe_white: '#FFF8D7', ui_font_yellow: '#FFD700', ui_font_faded_grey_beige: '#A99F89',
    ui_font_inactive_grey: '#666666', ui_font_inactive_grey_light: '#C0C0C0', ui_font_brown: '#4D3019', help_page_link_inactive: '#FFE77F',
};
