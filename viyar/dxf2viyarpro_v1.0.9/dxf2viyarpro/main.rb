require 'sketchup.rb'

module VP
  module DXF

    LANG = ::VP::DXF.lang

    def self.delete_non_abf_flatten
      model = Sketchup.active_model
      model.start_operation(LANG["Delete everything except flatten"])
      model.entities.each do |entity|
        unless (entity.is_a?(Sketchup::ComponentInstance) || entity.is_a?(Sketchup::Group)) && entity.name == "ABF_Flatten"
          begin
            entity.erase!
          rescue
          end
        end
      end
      model.definitions.purge_unused
      model.layers.purge_unused if model.layers.respond_to?(:purge_unused)
      model.layers.purge_unused_folders if model.layers.respond_to?(:purge_unused_folders)
      model.styles.purge_unused
      model.materials.purge_unused
      model.commit_operation
    end

    def self.find_abf_flatten_instances
      Sketchup.active_model.entities.select do |entity|
        entity.is_a?(Sketchup::Group) && entity.name == "ABF_Flatten"
      end
    end

    def self.delete_abf_flatten
      model = Sketchup.active_model
      model.start_operation(LANG["Delete flatten"])
      model.entities.each do |entity|
        if (entity.is_a?(Sketchup::ComponentInstance) || entity.is_a?(Sketchup::Group)) && entity.name == "ABF_Flatten"
          entity.erase!
        end
      end
      model.commit_operation
    end

    def self.export_dxf
      status = false
      model = Sketchup.active_model
      options_hash = {
        show_summary: false,
        acad_version: "acad_2007",
        faces_flag: true,
        text: false
      }

      file_name = model.title.empty? ? "untitled" : model.title
      file_path = UI.savepanel(LANG["Export flatten to DXF"], "", (file_name + LANG[" flatten.dxf"]).strip)
      if file_path
        file_path += ".dxf" unless file_path.downcase.end_with?(".dxf")
        begin
          status = model.export(file_path, options_hash)
          UI.messagebox(status ? LANG["DXF flatten has been exported succesfull!"] : LANG["Export error!"])
        rescue
          UI.messagebox(LANG["Unexpected export error!"])
        end
      end
      status
    end

    def self.main
      if self.find_abf_flatten_instances.empty?
        UI.messagebox(LANG["There is no flatten. In the ABF extension, click the Flatten button on the toolbar"])
        return
      end

      self.delete_non_abf_flatten
      export_status = self.export_dxf
      Sketchup.undo
      self.delete_abf_flatten if export_status
    end

    unless file_loaded?(__FILE__)
      menu = UI.menu('Plugins')
      menu.add_item(LANG["Export DXF for ViyarPro"]) {
        self.main
      }

      toolbar = UI::Toolbar.new "DXF2VIYARPRO"
      cmd = UI::Command.new(LANG["Export DXF for ViyarPro"]) {
        self.main
      }
      cmd.small_icon = "img/icon-72x72.png"
      cmd.large_icon = "img/icon-114x114.png"
      cmd.tooltip = LANG["Export DXF for ViyarPro"]
      cmd.status_bar_text = LANG["Flatten exporting"]
      toolbar.add_item cmd
      toolbar.show

      file_loaded(__FILE__)
    end

  end
end
