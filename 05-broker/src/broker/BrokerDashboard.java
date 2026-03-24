package broker;

import javax.swing.*;
import javax.swing.border.LineBorder;
import java.awt.*;
import java.util.*;

public class BrokerDashboard {
    private BrokerRemote service;
    private JFrame frame;
    private JPanel gridPanel;
    private JLabel infoLabel;
    private Map<String, SaleRow> saleRows = new LinkedHashMap<>();
    
    private static final Color COLOR_BG = new Color(10, 14, 39);
    private static final Color COLOR_GRAY = new Color(141, 141, 141);
    private static final Color COLOR_BLUE = new Color(44, 107, 237);
    private static final Color COLOR_ORANGE = new Color(242, 139, 37);
    private static final Color COLOR_GREEN = new Color(43, 191, 106);
    private static final int CELL_WIDTH = 100;
    private static final int CELL_HEIGHT = 50;
    
    public BrokerDashboard(BrokerRemote service) {
        this.service = service;
    }
    
    public void show() {
        SwingUtilities.invokeLater(() -> {
            frame = new JFrame("Broker RMI - Estados de venta");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setSize(1000, 500);
            frame.setLocationRelativeTo(null);
            
            gridPanel = new JPanel();
            gridPanel.setBackground(COLOR_BG);
            gridPanel.setLayout(new BoxLayout(gridPanel, BoxLayout.Y_AXIS));

            infoLabel = new JLabel("Esperando eventos del broker...");
            infoLabel.setForeground(Color.WHITE);
            infoLabel.setBorder(BorderFactory.createEmptyBorder(8, 10, 8, 10));
            infoLabel.setOpaque(true);
            infoLabel.setBackground(COLOR_BG);
            
            JScrollPane scrollPane = new JScrollPane(gridPanel);
            scrollPane.getViewport().setBackground(COLOR_BG);
            scrollPane.setBackground(COLOR_BG);
            
            frame.setLayout(new BorderLayout());
            frame.add(infoLabel, BorderLayout.NORTH);
            frame.add(scrollPane, BorderLayout.CENTER);
            frame.setVisible(true);
            
            javax.swing.Timer timer = new javax.swing.Timer(120, e -> refresh());
            timer.start();
        });
    }
    
    private Color statusToColor(String status) {
        if (status == null) return COLOR_GRAY;
        switch (status) {
            case "blue": return COLOR_BLUE;
            case "orange": return COLOR_ORANGE;
            case "green": return COLOR_GREEN;
            default: return COLOR_GRAY;
        }
    }
    
    private void refresh() {
        SwingUtilities.invokeLater(() -> {
            try {
                BrokerSnapshot snapshot = service.getSnapshot();
                
                for (SaleStatus sale : snapshot.sales) {
                    if (!saleRows.containsKey(sale.saleId)) {
                        SaleRow row = new SaleRow(sale);
                        saleRows.put(sale.saleId, row);
                        gridPanel.add(row.getPanel());
                    }
                    saleRows.get(sale.saleId).update(sale);
                }

                infoLabel.setText("Ventas monitoreadas: " + snapshot.sales.size() + " | Refresco: 120 ms");
                
                gridPanel.revalidate();
                gridPanel.repaint();
            } catch (Exception ignored) {
                // Ignore RMI errors
            }
        });
    }
    
    private class SaleRow {
        private JPanel panel;
        private JPanel serverPanel;
        private JPanel statusPanel;
        private JPanel clientsPanel;
        private Map<Integer, JPanel> clientCells = new HashMap<>();
        
        SaleRow(SaleStatus sale) {
            panel = new JPanel();
            panel.setLayout(new BoxLayout(panel, BoxLayout.X_AXIS));
            panel.setBackground(COLOR_BG);
            panel.setMaximumSize(new Dimension(Integer.MAX_VALUE, CELL_HEIGHT + 10));
            panel.setBorder(BorderFactory.createEmptyBorder(5, 5, 5, 5));
            
            // Panel del servidor (Sale ID)
            serverPanel = new JPanel();
            serverPanel.setLayout(new BorderLayout());
            serverPanel.setBackground(COLOR_GRAY);
            serverPanel.setPreferredSize(new Dimension(150, CELL_HEIGHT));
            serverPanel.setMaximumSize(new Dimension(150, CELL_HEIGHT));
            serverPanel.setMinimumSize(new Dimension(150, CELL_HEIGHT));
            
            JLabel serverLabel = new JLabel(sale.saleId);
            serverLabel.setForeground(Color.WHITE);
            serverLabel.setFont(new Font("Arial", Font.BOLD, 11));
            serverLabel.setHorizontalAlignment(JLabel.CENTER);
            serverLabel.setVerticalAlignment(JLabel.CENTER);
            serverPanel.add(serverLabel, BorderLayout.CENTER);
            panel.add(serverPanel);
            panel.add(Box.createHorizontalStrut(5));
            
            // Panel de estado
            statusPanel = new JPanel();
            statusPanel.setLayout(new BorderLayout());
            statusPanel.setBackground(COLOR_GRAY);
            statusPanel.setPreferredSize(new Dimension(80, CELL_HEIGHT));
            statusPanel.setMaximumSize(new Dimension(80, CELL_HEIGHT));
            statusPanel.setMinimumSize(new Dimension(80, CELL_HEIGHT));
            
            JLabel statusLabel = new JLabel("GRAY");
            statusLabel.setForeground(Color.WHITE);
            statusLabel.setFont(new Font("Arial", Font.BOLD, 9));
            statusLabel.setHorizontalAlignment(JLabel.CENTER);
            statusLabel.setVerticalAlignment(JLabel.CENTER);
            statusPanel.add(statusLabel, BorderLayout.CENTER);
            panel.add(statusPanel);
            panel.add(Box.createHorizontalStrut(5));
            
            // Panel de clientes
            clientsPanel = new JPanel();
            clientsPanel.setLayout(new FlowLayout(FlowLayout.LEFT, 3, 0));
            clientsPanel.setBackground(COLOR_BG);
            panel.add(clientsPanel);
        }
        
        void update(SaleStatus sale) {
            // Actualizar estado
            if (statusPanel != null && statusPanel.getComponentCount() > 0) {
                Component comp = statusPanel.getComponent(0);
                if (comp instanceof JLabel) {
                    JLabel label = (JLabel) comp;
                    label.setText(sale.status.toUpperCase());
                    statusPanel.setBackground(statusToColor(sale.status));
                }
            }
            
            // Actualizar o crear celdas de clientes
            int expectedClients = sale.expectedClients;
            int connectedClients = sale.connectedClients;
            
            for (int i = 0; i < expectedClients; i++) {
                if (!clientCells.containsKey(i)) {
                    JPanel clientCell = new JPanel();
                    clientCell.setLayout(new BorderLayout());
                    clientCell.setBorder(new LineBorder(new Color(100, 100, 100), 1));
                    clientCell.setPreferredSize(new Dimension(CELL_WIDTH, CELL_HEIGHT));
                    
                    JLabel label = new JLabel("C" + (i + 1));
                    label.setFont(new Font("Arial", Font.BOLD, 9));
                    label.setHorizontalAlignment(JLabel.CENTER);
                    label.setVerticalAlignment(JLabel.CENTER);
                    label.setForeground(Color.WHITE);
                    clientCell.add(label, BorderLayout.CENTER);
                    
                    clientCells.put(i, clientCell);
                    clientsPanel.add(clientCell);
                }
                
                JPanel cell = clientCells.get(i);
                cell.setBackground(i < connectedClients ? COLOR_BLUE : COLOR_GRAY);
            }
        }
        
        JPanel getPanel() {
            return panel;
        }
    }
}
